"""Coverage for corrected_outdoor_temp (v0.20.0)."""
from __future__ import annotations

import pytest

from app.weather.correction import corrected_outdoor_temp


# A realistic bias curve derived from the v0.19 calibration data. Peaks
# at 10:00 BST (+7.68), collapses through the afternoon, small overnight
# offset from urban microclimate.
BIAS = [
    1.66, 2.15, 2.59, 2.88, 3.12, 3.44, 4.29, 6.09, 7.56, 8.43, 7.68, 5.74,
    3.79, 2.41, 1.49, 0.98, 0.27, -0.02, -0.08, -0.01, 0.21, 0.66, 1.21, 1.47,
]
BASELINE = 1.5
FLOOR = 0.15


def test_no_calibration_returns_raw():
    assert corrected_outdoor_temp(30.0, 10, 20.0, None, BASELINE, FLOOR) == 30.0


def test_bias_at_baseline_returns_raw():
    # 15:00 = +0.98°C bias, below baseline 1.5 → no correction.
    assert corrected_outdoor_temp(28.0, 15, 20.0, BIAS, BASELINE, FLOOR) == 28.0


def test_peak_morning_sunny_day():
    # 10:00 = +7.68°C bias, excess = 6.18. Clear sky (cloud 5%) → clearness ~0.95.
    # 32.0 - 6.18 * 0.95 = 32.0 - 5.87 = 26.13
    corrected = corrected_outdoor_temp(32.0, 10, 5.0, BIAS, BASELINE, FLOOR)
    assert corrected == pytest.approx(26.13, abs=0.01)


def test_peak_morning_cloudy_day_uses_floor():
    # 10:00 same bias but fully overcast → clearness = max(0.15, 0) = 0.15.
    # 32.0 - 6.18 * 0.15 = 31.073
    corrected = corrected_outdoor_temp(32.0, 10, 100.0, BIAS, BASELINE, FLOOR)
    assert corrected == pytest.approx(31.07, abs=0.01)


def test_partial_cloud_scales_correction():
    # 50% cloud → clearness 0.5. Correction is half of clear-sky.
    corrected = corrected_outdoor_temp(32.0, 10, 50.0, BIAS, BASELINE, FLOOR)
    # excess=6.18, correction = 6.18 * 0.5 = 3.09, result = 28.91
    assert corrected == pytest.approx(28.91, abs=0.01)


def test_missing_cloud_uses_conservative_floor():
    # No cloud info: apply floor only (0.15) so we don't over-correct blind.
    corrected = corrected_outdoor_temp(32.0, 10, None, BIAS, BASELINE, FLOOR)
    assert corrected == pytest.approx(32.0 - 6.18 * 0.15, abs=0.01)


def test_afternoon_no_excess():
    # 16:00 = +0.27°C bias → below baseline → no correction even in full sun.
    assert corrected_outdoor_temp(28.0, 16, 0.0, BIAS, BASELINE, FLOOR) == 28.0


def test_overnight_no_excess():
    # 03:00 = +2.88°C bias > baseline 1.5, so excess = 1.38.
    # BUT at 3am there's no sun to apply the correction against; cloud=100 → floor.
    # excess 1.38 * 0.15 = 0.207
    corrected = corrected_outdoor_temp(22.0, 3, 100.0, BIAS, BASELINE, FLOOR)
    assert corrected == pytest.approx(22.0 - 1.38 * 0.15, abs=0.01)


def test_negative_bias_returns_raw():
    # 17:00 = -0.02°C: sensor reads LOWER than Met.no. excess < 0, no strip.
    assert corrected_outdoor_temp(28.0, 17, 5.0, BIAS, BASELINE, FLOOR) == 28.0


def test_bad_hour_returns_raw():
    assert corrected_outdoor_temp(30.0, -1, 20.0, BIAS, BASELINE, FLOOR) == 30.0
    assert corrected_outdoor_temp(30.0, 24, 20.0, BIAS, BASELINE, FLOOR) == 30.0


def test_wrong_length_bias_returns_raw():
    assert corrected_outdoor_temp(30.0, 10, 20.0, [0.0] * 12, BASELINE, FLOOR) == 30.0


def test_cloud_above_100_clamped():
    # Sanity: bogus cloud=150 → clamped to 100 → floor.
    corrected = corrected_outdoor_temp(32.0, 10, 150.0, BIAS, BASELINE, FLOOR)
    assert corrected == pytest.approx(32.0 - 6.18 * 0.15, abs=0.01)


def test_cloud_below_zero_clamped():
    corrected = corrected_outdoor_temp(32.0, 10, -10.0, BIAS, BASELINE, FLOOR)
    # -10 clamps to 0 → clearness = 1.0
    assert corrected == pytest.approx(32.0 - 6.18, abs=0.01)


def test_higher_baseline_shrinks_correction():
    # If we trust microclimate more (baseline=3.0), less bias is treated as artifact.
    # 10:00 bias 7.68, excess = 7.68 - 3.0 = 4.68 * 1.0 (clear) = 4.68
    corrected = corrected_outdoor_temp(32.0, 10, 0.0, BIAS, 3.0, FLOOR)
    assert corrected == pytest.approx(27.32, abs=0.01)


def test_zero_floor_zero_correction_on_overcast():
    # If user sets floor=0.0 and it's fully cloudy → zero correction.
    corrected = corrected_outdoor_temp(32.0, 10, 100.0, BIAS, BASELINE, 0.0)
    assert corrected == 32.0
