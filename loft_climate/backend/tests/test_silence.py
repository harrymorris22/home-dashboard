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
    import heat. Silence must explicitly report the temps."""
    f = _facts(
        cfg,
        weather=_weather(temp_c=27.5),
        house_avg_temp=26.4,
        outdoor="hot_out",
    )
    result = explain_silence_window("mezzanine", f)
    assert "27.5" in result
    assert "26.4" in result
    assert "import heat" in result


def test_window_none_outdoor_label(cfg):
    f = _facts(cfg, outdoor=None)
    assert "Outdoor category unavailable" in explain_silence_window("mezzanine", f)


def test_window_comfort_fallback(cfg):
    """Outdoor is meaningfully cooler than indoor but no cross-vent rule
    fires here (silence is only called when rules don't). Fallback branch."""
    f = _facts(cfg, weather=_weather(temp_c=18.0), house_avg_temp=22.0)
    # 18 < 22 - 1.5 → doesn't trigger the 'import heat' branch
    result = explain_silence_window("mezzanine", f)
    assert "Comfort band met" in result


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
    ("window_fallback", explain_silence_window,
     {"weather": _weather(temp_c=18.0), "house_avg_temp": 22.0}),
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
