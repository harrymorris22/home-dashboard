"""Coverage for the outdoor bias calibrator (v0.20.0)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.outdoor.calibrator import (
    CalibrationResult,
    fit_bias_curve,
    _join_by_local_hour,
)

LONDON = ZoneInfo("Europe/London")


def _dt(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_join_by_local_hour_bst_conversion():
    # Summer: UTC+1. A UTC 09:00 reading is BST 10:00.
    sensor = [(_dt(2026, 7, 15, 9, 0), 30.0)]
    weather = [(_dt(2026, 7, 15, 9, 30), 22.0)]
    bias, counts = _join_by_local_hour(sensor, weather, LONDON)
    assert counts[10] == 1  # bucketed into BST hour 10
    assert bias[10] == pytest.approx(8.0)


def test_join_averages_multiple_samples_per_hour():
    # 3 sensor samples in same BST hour → mean; 2 weather samples same → mean
    sensor = [
        (_dt(2026, 7, 15, 9, 0), 30.0),   # BST 10:00
        (_dt(2026, 7, 15, 9, 20), 32.0),  # BST 10:00
        (_dt(2026, 7, 15, 9, 40), 34.0),  # BST 10:00
    ]
    weather = [
        (_dt(2026, 7, 15, 9, 0), 22.0),
        (_dt(2026, 7, 15, 9, 30), 24.0),
    ]
    bias, counts = _join_by_local_hour(sensor, weather, LONDON)
    # sensor mean 32.0, weather mean 23.0 → bias 9.0
    assert bias[10] == pytest.approx(9.0)
    assert counts[10] == 1  # one day-hour pair contributed


def test_join_averages_across_multiple_days():
    # Same BST hour on 2 different days → each contributes one bias value,
    # the hourly average is the mean of the two days' biases.
    sensor = [
        (_dt(2026, 7, 15, 9, 0), 30.0),  # day 1: BST 10:00
        (_dt(2026, 7, 16, 9, 0), 34.0),  # day 2: BST 10:00
    ]
    weather = [
        (_dt(2026, 7, 15, 9, 0), 22.0),  # bias 8
        (_dt(2026, 7, 16, 9, 0), 26.0),  # bias 8
    ]
    bias, counts = _join_by_local_hour(sensor, weather, LONDON)
    assert bias[10] == pytest.approx(8.0)
    assert counts[10] == 2


def test_join_skips_hours_with_no_weather_pair():
    # Sensor has data at BST 10, weather has none → no bias entry for hour 10.
    sensor = [(_dt(2026, 7, 15, 9, 0), 30.0)]
    weather = [(_dt(2026, 7, 15, 12, 0), 22.0)]  # BST 13:00 only
    bias, counts = _join_by_local_hour(sensor, weather, LONDON)
    assert counts[10] == 0  # no join
    assert counts[13] == 0  # weather-only, no sensor pair


@pytest.mark.asyncio
async def test_fit_bias_curve_shape():
    # 7 days of synthetic data. Sensor overshoots by +6°C at BST 10 on sunny
    # days; matches Met.no at BST 16 as expected.
    sensor_points = []
    weather_points = []
    for day in range(7):
        base = datetime(2026, 7, 10 + day, 9, 0, tzinfo=timezone.utc)  # BST 10
        sensor_points.append((base, 30.0))
        weather_points.append((base, 24.0))
        base2 = datetime(2026, 7, 10 + day, 15, 0, tzinfo=timezone.utc)  # BST 16
        sensor_points.append((base2, 28.0))
        weather_points.append((base2, 28.0))

    async def _sensor(start, end):
        return sensor_points

    def _weather(start, end):
        return weather_points

    result = await fit_bias_curve(_sensor, _weather, LONDON, days_window=7)
    assert isinstance(result, CalibrationResult)
    assert len(result.bias_by_hour) == 24
    assert len(result.sample_counts) == 24
    assert result.days_window == 7
    assert result.bias_by_hour[10] == pytest.approx(6.0)
    assert result.bias_by_hour[16] == pytest.approx(0.0)
    assert result.sample_counts[10] == 7
    assert result.sample_counts[16] == 7
    # Untouched hours: zero bias, zero samples.
    assert result.bias_by_hour[3] == 0.0
    assert result.sample_counts[3] == 0


@pytest.mark.asyncio
async def test_fit_bias_curve_empty_data_zero_result():
    async def _sensor(start, end):
        return []

    def _weather(start, end):
        return []

    result = await fit_bias_curve(_sensor, _weather, LONDON, days_window=30)
    assert result.bias_by_hour == [0.0] * 24
    assert result.sample_counts == [0] * 24


@pytest.mark.asyncio
async def test_fit_bias_curve_naive_datetime_treated_as_utc():
    """Data providers may return naive datetimes; the fit must not crash."""
    sensor_points = [(datetime(2026, 7, 15, 9, 0), 30.0)]  # naive
    weather_points = [(datetime(2026, 7, 15, 9, 30), 22.0)]  # naive

    async def _sensor(start, end):
        return sensor_points

    def _weather(start, end):
        return weather_points

    result = await fit_bias_curve(_sensor, _weather, LONDON, days_window=1)
    assert result.bias_by_hour[10] == pytest.approx(8.0)
