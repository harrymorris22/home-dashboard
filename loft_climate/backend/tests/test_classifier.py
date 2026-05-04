from datetime import datetime, timezone

from app.config.schema import ConfigV1
from app.engine.classifier import (
    build_facts,
    classify_outdoor,
    classify_sky,
    classify_solar_load,
    classify_wind,
    classify_zone_thermal,
)
from app.simulation.scenarios import (
    cold_cloudy,
    hot_sunny_breeze,
    hot_sunny_still,
    rain_override,
)


def test_zone_thermal_bands(cfg: ConfigV1):
    assert classify_zone_thermal(18.0, 19.0, 24.0) == "cold"
    assert classify_zone_thermal(22.0, 19.0, 24.0) == "comfortable"
    assert classify_zone_thermal(25.0, 19.0, 24.0) == "hot"


def test_outdoor_label(cfg: ConfigV1):
    snap = hot_sunny_breeze(cfg)
    label = classify_outdoor(snap.weather, cfg)
    assert label == "hot_out"


def test_sky_label_sunny(cfg: ConfigV1):
    snap = hot_sunny_breeze(cfg)
    assert classify_sky(snap.weather, cfg) == "sunny"


def test_sky_label_cloudy(cfg: ConfigV1):
    snap = cold_cloudy(cfg)
    assert classify_sky(snap.weather, cfg) == "cloudy"


def test_wind_label_breeze(cfg: ConfigV1):
    snap = hot_sunny_breeze(cfg)
    assert classify_wind(snap.weather, cfg) in ("breeze", "windy")


def test_wind_label_still(cfg: ConfigV1):
    snap = hot_sunny_still(cfg)
    assert classify_wind(snap.weather, cfg) == "still"


def test_solar_load_high(cfg: ConfigV1):
    snap = hot_sunny_breeze(cfg)
    assert classify_solar_load(snap.weather, cfg) == "high"


def test_facts_built_from_scenario(cfg: ConfigV1):
    snap = hot_sunny_breeze(cfg)
    f = build_facts(snap.now, snap.zones, snap.weather, snap.sun, snap.config)
    assert f.outdoor == "hot_out"
    assert f.sky == "sunny"
    assert f.sun_on_sw is True
    assert f.precip is False
    assert f.weather is not None


def test_facts_precip_flag(cfg: ConfigV1):
    snap = rain_override(cfg)
    f = build_facts(snap.now, snap.zones, snap.weather, snap.sun, snap.config)
    assert f.precip is True


def test_outdoor_none_when_weather_none(cfg: ConfigV1):
    assert classify_outdoor(None, cfg) is None
