"""Coverage for silence explainers.

Pure functions of Facts → diagnostic strings. No I/O.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.engine.silence import (
    SILENCE_MAX_CHARS,
    explain_silence_blind,
    explain_silence_window,
)
from app.engine.types import Facts
from app.weather.schema import WeatherSnapshot


def _weather(temp_c: float = 20.0) -> WeatherSnapshot:
    return WeatherSnapshot(
        fetched_at=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        temp_c=temp_c,
        feels_like_c=temp_c,
        humidity_pct=50.0,
        cloud_cover_pct=50.0,
        wind_speed_mps=2.0,
        wind_gust_mps=None,
        uvi=1.0,
        conditions="Clouds",
        precip_now=False,
        sunrise=datetime(2026, 5, 6, 5, 0, tzinfo=timezone.utc),
        sunset=datetime(2026, 5, 6, 20, 0, tzinfo=timezone.utc),
        hourly=[],
        stale=False,
    )


def _facts(cfg, **overrides):
    """Build a synthetic Facts. Sensible defaults; override any field."""
    base = dict(
        now=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        zone_thermal={"mezzanine": "comfortable", "downstairs": "comfortable",
                      "ceiling_apex": "comfortable", "bedroom": "comfortable"},
        zone_temp={"mezzanine": 22.0, "downstairs": 22.0,
                   "ceiling_apex": 22.0, "bedroom": 22.0},
        zone_humidity={z: 50.0 for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")},
        zone_apparent={z: 22.0 for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")},
        zone_lux={z: None for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")},
        outdoor="mild_out",
        sky="partly",
        wind="breeze",
        phase="midday",
        sun_on_sw=False,
        solar_load="low",
        bedtime_window=False,
        precip=False,
        weather=_weather(),
        config=cfg,
        house_avg_temp=22.0,
        apex_excess_c=0.0,
        forecast_max_c=None,
        sunset=datetime(2026, 5, 6, 20, 0, tzinfo=timezone.utc),
        sunrise=datetime(2026, 5, 6, 5, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Facts(**base)


# --- explain_silence_blind ------------------------------------------------


def test_blind_weather_offline(cfg):
    f = _facts(cfg, weather=None)
    assert "Weather offline" in explain_silence_blind("mezz", f)


def test_blind_night_phase(cfg):
    f = _facts(cfg, phase="night")
    assert "Night phase" in explain_silence_blind("mezz", f)


def test_blind_pre_dawn(cfg):
    f = _facts(cfg, phase="pre_dawn")
    assert "Night phase" in explain_silence_blind("mezz", f)


def test_blind_no_sun_on_sw(cfg):
    f = _facts(cfg, sun_on_sw=False)
    assert "Sun not on glazing" in explain_silence_blind("mezz", f)


def test_blind_sun_on_sw_low_solar_load(cfg):
    f = _facts(cfg, sun_on_sw=True, solar_load="low")
    assert explain_silence_blind("mezz", f) == "Comfort band met."


def test_blind_sun_on_sw_moderate_solar_load(cfg):
    f = _facts(cfg, sun_on_sw=True, solar_load="moderate")
    assert "comfort band met" in explain_silence_blind("mezz", f).lower()


# --- explain_silence_window -----------------------------------------------


def test_window_weather_offline(cfg):
    f = _facts(cfg, weather=None)
    assert "Weather offline" in explain_silence_window("mezzanine", f)


def test_window_empty_zone_temp_guards_zero_division(cfg):
    """REGRESSION: house_avg_temp defaults to 0.0 when zone_temp is empty
    (classifier.py:153). Without the guard, the delta line would incorrectly
    report 'outdoor > indoor' for any positive outdoor temp because
    indoor=0. Eng review flagged this as a medium-severity bug.
    """
    f = _facts(cfg, zone_temp={}, house_avg_temp=0.0)
    result = explain_silence_window("mezzanine", f)
    assert "Indoor sensors offline" in result


def test_window_precip(cfg):
    f = _facts(cfg, precip=True)
    assert "Rain" in explain_silence_window("mezzanine", f)


def test_window_cold_outdoor(cfg):
    f = _facts(cfg, outdoor="cold_out")
    assert "chill" in explain_silence_window("mezzanine", f).lower()


def test_window_outdoor_warmer_than_indoor(cfg):
    """The motivating bug: warm cloudy day where opening windows would
    import heat. Silence must explicitly report the temps — and use the
    ZONE's own temp (not house average), so each dashboard row reflects
    that zone's reality."""
    f = _facts(
        cfg,
        weather=_weather(temp_c=27.5),
        zone_temp={
            "mezzanine": 26.4, "downstairs": 26.4,
            "ceiling_apex": 26.4, "bedroom": 26.4,
        },
        house_avg_temp=26.4,
        outdoor="hot_out",
    )
    result = explain_silence_window("mezzanine", f)
    assert "27.5" in result
    assert "26.4" in result
    assert "import heat" in result


def test_window_per_zone_import_heat_uses_zone_temp(cfg):
    """REGRESSION (v0.17.0): each row's silence must reflect that zone's
    temp, not the house average. Bedroom cool while other zones are hot →
    bedroom row correctly says opening would import heat."""
    f = _facts(
        cfg,
        weather=_weather(temp_c=28.0),
        zone_temp={
            "mezzanine": 30.3, "downstairs": 28.4,
            "ceiling_apex": 30.0, "bedroom": 23.6,
        },
        house_avg_temp=28.075,  # average of the four
        outdoor="hot_out",
    )
    bedroom = explain_silence_window("bedroom", f)
    assert "23.6" in bedroom
    assert "28.0" in bedroom
    assert "import heat" in bedroom


def test_window_per_zone_would_vent(cfg):
    """REGRESSION (v0.17.0): when a zone is meaningfully hotter than
    outdoor but the house-average rule kept everything silent, the row
    must NOT claim 'import heat' — it should suggest manual venting."""
    f = _facts(
        cfg,
        weather=_weather(temp_c=28.0),
        zone_temp={
            "mezzanine": 30.3, "downstairs": 28.4,
            "ceiling_apex": 30.0, "bedroom": 23.6,
        },
        house_avg_temp=28.075,
        outdoor="hot_out",
    )
    office = explain_silence_window("mezzanine", f)
    assert "30.3" in office
    assert "28.0" in office
    assert "import heat" not in office
    assert "manually" in office


def test_window_zone_sensor_offline_falls_back_to_house_avg(cfg):
    """One zone's sensor is offline while others report — the row for the
    offline zone still gets some thermal frame via house average."""
    f = _facts(
        cfg,
        weather=_weather(temp_c=27.5),
        zone_temp={"downstairs": 26.4, "ceiling_apex": 26.4, "bedroom": 26.4},
        house_avg_temp=26.4,
        outdoor="hot_out",
    )
    result = explain_silence_window("mezzanine", f)
    assert "26.4" in result
    assert "Sensor offline" in result


def test_window_none_outdoor_label(cfg):
    f = _facts(cfg, outdoor=None)
    assert "Outdoor category unavailable" in explain_silence_window("mezzanine", f)


def test_window_cooler_outdoor_would_vent(cfg):
    """Outdoor meaningfully cooler than the zone → the rule normally fires,
    but if silence is invoked anyway (rule combiner edge cases), the row
    should suggest manual venting rather than fall through to a bland
    'comfort band met'."""
    f = _facts(
        cfg,
        weather=_weather(temp_c=18.0),
        zone_temp={
            "mezzanine": 22.0, "downstairs": 22.0,
            "ceiling_apex": 22.0, "bedroom": 22.0,
        },
        house_avg_temp=22.0,
    )
    result = explain_silence_window("mezzanine", f)
    assert "manually" in result


# --- length invariant ---------------------------------------------------


@pytest.mark.parametrize("kind,fn,facts_overrides", [
    ("blind_offline", explain_silence_blind, {"weather": None}),
    ("blind_night", explain_silence_blind, {"phase": "night"}),
    ("blind_no_sun", explain_silence_blind, {"sun_on_sw": False}),
    ("blind_sun_high_load", explain_silence_blind, {"sun_on_sw": True, "solar_load": "high"}),
    ("blind_fallback", explain_silence_blind, {"sun_on_sw": True, "solar_load": "low"}),
    ("window_offline", explain_silence_window, {"weather": None}),
    ("window_no_zones", explain_silence_window, {"zone_temp": {}, "house_avg_temp": 0.0}),
    ("window_precip", explain_silence_window, {"precip": True}),
    ("window_cold", explain_silence_window, {"outdoor": "cold_out"}),
    ("window_import_heat", explain_silence_window,
     {"weather": _weather(temp_c=27.5), "house_avg_temp": 26.4, "outdoor": "hot_out"}),
    ("window_none_outdoor", explain_silence_window, {"outdoor": None}),
    ("window_would_vent", explain_silence_window,
     {"weather": _weather(temp_c=18.0), "house_avg_temp": 22.0}),
    ("window_zone_offline", explain_silence_window,
     {"weather": _weather(temp_c=27.5), "outdoor": "hot_out",
      "zone_temp": {"downstairs": 26.4, "ceiling_apex": 26.4, "bedroom": 26.4},
      "house_avg_temp": 26.4}),
])
def test_silence_strings_within_length_cap(cfg, kind, fn, facts_overrides):
    """All silence strings must be ≤ SILENCE_MAX_CHARS (80). Design review
    flagged mobile-viewport wrap risk; the cap locks it."""
    f = _facts(cfg, **facts_overrides)
    # Pick sensible key based on function.
    key = "mezz" if fn is explain_silence_blind else "mezzanine"
    result = fn(key, f)
    assert len(result) <= SILENCE_MAX_CHARS, (
        f"[{kind}] silence string too long ({len(result)} chars): {result!r}"
    )
