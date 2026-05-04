from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ZONE_IDS = ("mezzanine", "downstairs", "ceiling_apex", "bedroom")
BLIND_GROUP_IDS = ("mezz", "downstairs", "bedroom")
ZoneId = Literal["mezzanine", "downstairs", "ceiling_apex", "bedroom"]
BlindGroupId = Literal["mezz", "downstairs", "bedroom"]


class Location(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    facing_azimuth_deg: float = 225.0


class ZoneConfig(BaseModel):
    comfort_min: float
    comfort_max: float
    blind_group: BlindGroupId | None = None
    stack_vent_delta_c: float | None = None
    bedtime_target_c: float | None = None
    bedtime_prep_minutes: int | None = None

    @model_validator(mode="after")
    def _comfort_band(self) -> ZoneConfig:
        if self.comfort_min >= self.comfort_max:
            raise ValueError(
                f"comfort_min ({self.comfort_min}) must be < comfort_max ({self.comfort_max})"
            )
        return self


class Schedule(BaseModel):
    bedtime_local: str
    wake_local: str

    @field_validator("bedtime_local", "wake_local")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}", v):
            raise ValueError(f"time must be HH:MM, got {v!r}")
        h, m = v.split(":")
        if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError(f"time out of range: {v!r}")
        return v


class Thermal(BaseModel):
    outdoor_hot_c: float
    outdoor_cold_c: float
    feels_like_weight: float = 1.0

    @model_validator(mode="after")
    def _band(self) -> Thermal:
        if self.outdoor_cold_c >= self.outdoor_hot_c:
            raise ValueError("outdoor_cold_c must be < outdoor_hot_c")
        return self


class Sky(BaseModel):
    sunny_max_cloud_pct: float
    cloudy_min_cloud_pct: float

    @model_validator(mode="after")
    def _band(self) -> Sky:
        if self.sunny_max_cloud_pct >= self.cloudy_min_cloud_pct:
            raise ValueError("sunny_max_cloud_pct must be < cloudy_min_cloud_pct")
        return self


class Wind(BaseModel):
    still_max_mps: float
    breeze_min_mps: float

    @model_validator(mode="after")
    def _band(self) -> Wind:
        if self.still_max_mps >= self.breeze_min_mps:
            raise ValueError("still_max_mps must be < breeze_min_mps")
        return self


class SunOnSW(BaseModel):
    azimuth_min_deg: float
    azimuth_max_deg: float
    elevation_min_deg: float
    lux_indoor_direct_threshold: float
    lux_indoor_diffuse_threshold: float

    @model_validator(mode="after")
    def _band(self) -> SunOnSW:
        if self.azimuth_min_deg >= self.azimuth_max_deg:
            raise ValueError("azimuth_min_deg must be < azimuth_max_deg")
        if self.lux_indoor_diffuse_threshold >= self.lux_indoor_direct_threshold:
            raise ValueError("diffuse threshold must be < direct threshold")
        return self


class Weather(BaseModel):
    fetch_interval_seconds: int = 600
    stale_after_seconds: int = 1800


class Air(BaseModel):
    suppress_purge_aqi_above: int = 3


class Engine(BaseModel):
    tie_breaker: Literal["no_change"] = "no_change"
    log_recommendations: bool = True
    dwell_minutes: int = 20
    stale_after_minutes: int = 90


class Solar(BaseModel):
    uvi_high: float = 6.0
    uvi_moderate: float = 3.0

    @model_validator(mode="after")
    def _band(self) -> Solar:
        if self.uvi_moderate >= self.uvi_high:
            raise ValueError("uvi_moderate must be < uvi_high")
        return self


class ConfigV1(BaseModel):
    version: Literal[1] = 1
    location: Location
    zones: dict[str, ZoneConfig]
    blind_groups: list[BlindGroupId]
    schedule: Schedule
    thermal: Thermal
    sky: Sky
    wind: Wind
    sun_on_sw: SunOnSW
    weather: Weather
    air: Air
    engine: Engine
    solar: Solar

    @model_validator(mode="after")
    def _zones_complete(self) -> ConfigV1:
        # Every required zone present.
        missing = [z for z in ZONE_IDS if z not in self.zones]
        if missing:
            raise ValueError(f"zones missing required entries: {missing}")
        # Bedroom-specific invariants.
        bedroom = self.zones.get("bedroom")
        if bedroom is None:
            raise ValueError("bedroom zone is required")
        if bedroom.bedtime_target_c is not None:
            if not (bedroom.comfort_min <= bedroom.bedtime_target_c <= bedroom.comfort_max):
                raise ValueError(
                    "bedroom.bedtime_target_c must lie within [comfort_min, comfort_max]"
                )
        return self
