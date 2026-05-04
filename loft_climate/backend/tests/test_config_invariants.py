import pytest
from pydantic import ValidationError

from app.config.loader import load_config
from app.config.schema import ConfigV1


def _config_dict():
    cfg = load_config()
    return cfg.model_dump(mode="json")


def test_default_loads():
    cfg = load_config()
    assert cfg.version == 1


def test_comfort_band_invariant():
    payload = _config_dict()
    payload["zones"]["mezzanine"]["comfort_min"] = 25.0
    payload["zones"]["mezzanine"]["comfort_max"] = 22.0
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_outdoor_band_invariant():
    payload = _config_dict()
    payload["thermal"]["outdoor_cold_c"] = 24.0
    payload["thermal"]["outdoor_hot_c"] = 18.0
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_sky_band_invariant():
    payload = _config_dict()
    payload["sky"]["sunny_max_cloud_pct"] = 90
    payload["sky"]["cloudy_min_cloud_pct"] = 10
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_wind_band_invariant():
    payload = _config_dict()
    payload["wind"]["still_max_mps"] = 5.0
    payload["wind"]["breeze_min_mps"] = 1.0
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_azimuth_band_invariant():
    payload = _config_dict()
    payload["sun_on_sw"]["azimuth_min_deg"] = 280
    payload["sun_on_sw"]["azimuth_max_deg"] = 100
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_bedtime_format():
    payload = _config_dict()
    payload["schedule"]["bedtime_local"] = "10pm"
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_bedtime_target_within_bedroom_band():
    payload = _config_dict()
    payload["zones"]["bedroom"]["bedtime_target_c"] = 30.0
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)


def test_lux_thresholds_ordered():
    payload = _config_dict()
    payload["sun_on_sw"]["lux_indoor_diffuse_threshold"] = 9999
    payload["sun_on_sw"]["lux_indoor_direct_threshold"] = 100
    with pytest.raises(ValidationError):
        ConfigV1.model_validate(payload)
