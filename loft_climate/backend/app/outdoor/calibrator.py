"""Fit the hour-of-day bias curve for the outdoor sensor.

Joins SwitchBot outdoor sensor history (from HA Recorder via REST) with
Met.no history (from our local ``weather_cache``), buckets both by
hour-of-day in the configured local timezone, and computes the per-hour
mean of ``switchbot − met_no``. Persists the fitted curve as an
``OutdoorBiasCalibration`` row.

Called from:
- The scheduler on a weekly cadence (``fit_interval_days``) and on first
  startup when no calibration row exists yet.
- The ``POST /api/outdoor/bias`` endpoint when a user forces a refit.

Pure enough to be testable: the two data sources are passed in as
callables so tests can stub them without HA / DB fixtures. The bucketing
and averaging is a plain reduction.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config.schema import ConfigV1
from app.db import repo
from app.db.models import OutdoorBiasCalibration

log = logging.getLogger(__name__)


HOURS = 24


@dataclass(frozen=True)
class CalibrationResult:
    fitted_at: datetime
    days_window: int
    bias_by_hour: list[float]  # length 24, per hour-of-day local
    sample_counts: list[int]   # length 24


def _bucket_by_local_hour(
    points: list[tuple[datetime, float]],
    tz: ZoneInfo,
) -> dict[int, list[float]]:
    """Bucket (ts, value) pairs into 0..23 by hour-of-day in ``tz``."""
    out: dict[int, list[float]] = {h: [] for h in range(HOURS)}
    for ts, v in points:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local_hour = ts.astimezone(tz).hour
        out[local_hour].append(v)
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _join_by_local_hour(
    sensor_points: list[tuple[datetime, float]],
    weather_points: list[tuple[datetime, float]],
    tz: ZoneInfo,
) -> tuple[list[float], list[int]]:
    """Pair the two series by rounded local-hour timestamp, per-hour mean.

    Rather than aligning individual (ts_sensor, ts_weather) pairs — which
    would require nearest-neighbour lookups — we bucket both series
    independently by (date, hour_of_day) and compare the per-hour means.
    That matches how the source data was analysed in the notebook that
    validated this approach and is robust to differing sample rates
    (SwitchBot updates every few minutes, Met.no every 10).
    """
    def _keyed(points: list[tuple[datetime, float]]) -> dict[tuple[str, int], list[float]]:
        buckets: dict[tuple[str, int], list[float]] = {}
        for ts, v in points:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            local = ts.astimezone(tz)
            key = (local.date().isoformat(), local.hour)
            buckets.setdefault(key, []).append(v)
        return buckets

    sensor_by = _keyed(sensor_points)
    weather_by = _keyed(weather_points)

    bias_bins: dict[int, list[float]] = {h: [] for h in range(HOURS)}
    for key in sensor_by.keys() & weather_by.keys():
        _, hour = key
        bias = _mean(sensor_by[key]) - _mean(weather_by[key])
        bias_bins[hour].append(bias)

    bias_by_hour = [round(_mean(bias_bins[h]), 3) for h in range(HOURS)]
    sample_counts = [len(bias_bins[h]) for h in range(HOURS)]
    return bias_by_hour, sample_counts


async def fit_bias_curve(
    fetch_sensor_history: Callable[
        [datetime, datetime], Awaitable[list[tuple[datetime, float]]]
    ],
    fetch_weather_history: Callable[
        [datetime, datetime], list[tuple[datetime, float]]
    ],
    tz: ZoneInfo,
    days_window: int,
    now: datetime | None = None,
) -> CalibrationResult:
    """Compute a fresh bias curve from the last ``days_window`` days.

    Data fetchers are injected so this can be tested without HA / DB.
    Returns a CalibrationResult even if data is thin — the caller decides
    whether to persist it (typically it will, and the sample_counts array
    tells the frontend how confident each hour is).
    """
    now = now or datetime.now(tz=timezone.utc)
    start = now - timedelta(days=days_window)
    sensor_points = await fetch_sensor_history(start, now)
    weather_points = fetch_weather_history(start, now)
    bias_by_hour, sample_counts = _join_by_local_hour(
        sensor_points, weather_points, tz
    )
    return CalibrationResult(
        fitted_at=now,
        days_window=days_window,
        bias_by_hour=bias_by_hour,
        sample_counts=sample_counts,
    )


def persist_calibration(
    session: Session, result: CalibrationResult
) -> OutdoorBiasCalibration:
    row = OutdoorBiasCalibration(
        fitted_at=result.fitted_at,
        days_window=result.days_window,
        bias_by_hour_json=json.dumps(result.bias_by_hour),
        sample_counts_json=json.dumps(result.sample_counts),
    )
    repo.insert_outdoor_calibration(session, row)
    session.commit()
    log.info(
        "[outdoor-calibrator] persisted bias curve id=%s window=%dd samples/hr=%s",
        row.id,
        result.days_window,
        result.sample_counts,
    )
    return row


async def run_calibration(
    session: Session,
    ha_client,
    cfg: ConfigV1,
    outdoor_temp_entity: str,
) -> OutdoorBiasCalibration | None:
    """Full end-to-end: pull both series, fit, persist. Returns None on
    empty data (nothing to persist)."""
    tz = ZoneInfo(cfg.location.timezone)
    window = cfg.outdoor.fit_window_days

    async def _sensor(start: datetime, end: datetime):
        try:
            return await ha_client.history_period(outdoor_temp_entity, start, end)
        except Exception as e:
            log.warning("[outdoor-calibrator] HA history fetch failed: %s", e)
            return []

    def _weather(start: datetime, end: datetime):
        rows = repo.weather_rows_range(session, start, end)
        points: list[tuple[datetime, float]] = []
        for row in rows:
            try:
                payload = json.loads(row.payload_json)
                temp = payload.get("temp_c")
                if temp is not None:
                    ts = row.fetched_at
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    points.append((ts, float(temp)))
            except (ValueError, TypeError):
                continue
        return points

    result = await fit_bias_curve(_sensor, _weather, tz, window)
    if sum(result.sample_counts) == 0:
        log.info("[outdoor-calibrator] no joined data yet, skipping persist")
        return None
    return persist_calibration(session, result)
