from datetime import datetime, timezone

from app.config.schema import ConfigV1
from app.sun.calculator import compute, is_sun_on_sw


def test_summer_afternoon_london(cfg: ConfigV1):
    # 14:00 BST = 13:00 UTC, mid July
    when = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert 30 < pos.elevation_deg < 60
    assert 200 <= pos.azimuth_deg <= 240
    assert pos.is_daylight


def test_midnight_below_horizon(cfg: ConfigV1):
    when = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert pos.elevation_deg < 0
    assert not pos.is_daylight


def test_is_sun_on_sw_geometry(cfg: ConfigV1):
    when = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert is_sun_on_sw(pos, cfg) is True


def test_is_sun_on_sw_below_horizon_false(cfg: ConfigV1):
    when = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert is_sun_on_sw(pos, cfg) is False
    # Even with high lux, below-horizon stays false.
    assert is_sun_on_sw(pos, cfg, lux_indoor=99999) is False


def test_is_sun_on_sw_off_azimuth(cfg: ConfigV1):
    # Early morning: sun is in the east (~90°), not SW.
    when = datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert is_sun_on_sw(pos, cfg) is False
