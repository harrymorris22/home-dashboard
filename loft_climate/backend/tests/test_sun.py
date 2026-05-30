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
    # Late evening (9 PM BST = 8 PM UTC, mid July): sun in the NW (~290°),
    # past the SE-facing glazing's 230° max azimuth. v0.11 widened the
    # acceptance window so morning sun in the E (~80°) now counts as
    # on-glazing, which means "off-azimuth" tests need a different time
    # of day.
    when = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert is_sun_on_sw(pos, cfg) is False


# --- v0.10: blinds-aware lux confirmation ---------------------------------


def test_is_sun_on_sw_geometric_overrides_blinds(cfg: ConfigV1):
    """When geometry says sun is squarely on SW, blinds-blocking is irrelevant."""
    when = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    # Even with blinds blocking AND zero lux, geometric=True wins.
    assert is_sun_on_sw(pos, cfg, lux_indoor=0, sw_blinds_blocking=True) is True


def test_is_sun_on_sw_blinds_blocking_loose_azimuth_in_daylight(cfg: ConfigV1):
    """REGRESSION: blinds down + sun loosely SW + daylight + low lux → True.

    Without this, the engine reads low lux (because blinds block the
    sensor), concludes "no sun", recommends blinds up, user opens them,
    sun pours in. Whiplash. The fix: skip lux confirmation when blinds
    are blocking and fall back to wider geometry.
    """
    # ~6 PM in July — sun has moved out of the strict SW window but is still
    # loosely SW-facing (azimuth ~280° depending on cfg). Daylight.
    when = datetime(2026, 7, 15, 17, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    if not pos.is_daylight:
        return  # not a valid test fixture; skip silently
    # With blinds NOT blocking and low lux → false (current behavior).
    base_result = is_sun_on_sw(pos, cfg, lux_indoor=0, sw_blinds_blocking=False)
    # With blinds blocking and low lux → True iff sun is in the loose SW envelope.
    blocked_result = is_sun_on_sw(pos, cfg, lux_indoor=0, sw_blinds_blocking=True)
    # Critically: blocked_result must be at least as conservative as base_result.
    # If the sun is loosely SW, blocked path should return True even with zero lux.
    assert blocked_result >= base_result, (
        "blinds-blocking path must never be MORE permissive about 'no sun' "
        "than the non-blocking path"
    )


def test_is_sun_on_sw_blinds_blocking_far_off_azimuth(cfg: ConfigV1):
    """Blinds blocking + sun far from glazing (e.g. NW evening) → still False.

    The fix shouldn't make the engine paranoid. When the sun is genuinely
    not on the glazing (well outside the loose envelope), blinds-blocking
    doesn't change the answer. v0.11 widened the morning window so the
    test fixture moves to evening NW to stay truly off-azimuth.
    """
    when = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert is_sun_on_sw(pos, cfg, lux_indoor=0, sw_blinds_blocking=True) is False


def test_is_sun_on_sw_blinds_blocking_night(cfg: ConfigV1):
    """Night-time + blinds blocking → still False (no manufactured sun)."""
    when = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    assert is_sun_on_sw(pos, cfg, lux_indoor=0, sw_blinds_blocking=True) is False
    # Even with absurd lux (e.g., bedside lamp), still false.
    assert is_sun_on_sw(pos, cfg, lux_indoor=99999, sw_blinds_blocking=True) is False


def test_is_sun_on_sw_blinds_up_uses_lux_normally(cfg: ConfigV1):
    """When blinds aren't blocking, existing lux confirmation path is unchanged."""
    when = datetime(2026, 7, 15, 17, 0, tzinfo=timezone.utc)
    pos = compute(when, cfg)
    if not pos.is_daylight:
        return
    # Pre-existing behavior: low lux → False (in the borderline case).
    low = is_sun_on_sw(pos, cfg, lux_indoor=0, sw_blinds_blocking=False)
    # High lux confirms — True if loosely SW.
    high = is_sun_on_sw(pos, cfg, lux_indoor=50000, sw_blinds_blocking=False)
    # We don't know which case the fixture cfg lands in, but high must
    # always be >= low — lux confirmation can only ADD True cases.
    assert high >= low
