from __future__ import annotations

import re
from datetime import datetime
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


class Notifications(BaseModel):
    enabled: bool = True
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "07:00"
    cooldown_minutes: int = Field(default=30, ge=5, le=1440)
    transition_window_minutes: int = Field(default=15, ge=1, le=60)
    red_bypass_quiet_hours: bool = True
    sustained_weather_offline_ticks: int = Field(default=3, ge=1, le=20)
    staleness_days: int = Field(default=7, ge=1, le=90)
    snooze_until: datetime | None = None  # ISO timestamp; null = no snooze

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}", v):
            raise ValueError(f"time must be HH:MM, got {v!r}")
        h, m = v.split(":")
        if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError(f"time out of range: {v!r}")
        return v

    @model_validator(mode="after")
    def _band(self) -> Notifications:
        if self.quiet_hours_start == self.quiet_hours_end:
            raise ValueError("quiet_hours_start must differ from quiet_hours_end")
        return self


class Solar(BaseModel):
    uvi_high: float = 6.0
    uvi_moderate: float = 3.0

    @model_validator(mode="after")
    def _band(self) -> Solar:
        if self.uvi_moderate >= self.uvi_high:
            raise ValueError("uvi_moderate must be < uvi_high")
        return self


class Outdoor(BaseModel):
    """Bias-correction of the outdoor sensor reading.

    The SwitchBot outdoor sensor absorbs direct sun during morning hours,
    reading up to +8°C over true air temp (see v0.19 calibration data).
    This section models the artifact so the raw sensor value can be
    corrected before entering the vent-decision rules. See
    ``app/weather/correction.py``.

    correction:
      - ``sensor_only``: return the raw sensor reading, no correction.
      - ``sensor_bias_corrected`` (default): subtract the excess bias
        (fitted hourly curve minus microclimate baseline) scaled by how
        clear the sky is right now.

    microclimate_baseline_c: overnight/no-sun bias between sensor and
      Met.no. Kept as-is because it reflects real building-vs-grid-cell
      microclimate. Only bias *above* this baseline is treated as a sensor
      artifact and subtracted.

    clearness_floor: minimum multiplier applied to the excess bias even
      on fully-overcast days. Captures the residual heating from diffuse
      radiation reaching the sensor casing.

    fit_window_days: how many days of joined SwitchBot + Met.no history
      the calibrator uses to fit the hourly bias curve. 30 gives a stable
      average without lagging seasonal sun-angle drift too badly.

    fit_interval_days: how often the scheduler re-fits the curve. Weekly
      keeps the correction current as sun angle drifts across the year.
    """
    correction: Literal["sensor_only", "sensor_bias_corrected"] = "sensor_bias_corrected"
    microclimate_baseline_c: float = 1.5
    clearness_floor: float = Field(default=0.15, ge=0.0, le=1.0)
    fit_window_days: int = Field(default=30, ge=7, le=90)
    fit_interval_days: int = Field(default=7, ge=1, le=30)


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
    outdoor: Outdoor = Field(default_factory=Outdoor)
    notifications: Notifications = Field(default_factory=Notifications)

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
