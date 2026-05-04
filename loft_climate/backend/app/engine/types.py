from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.config.schema import ConfigV1
from app.sensors.source import ZoneSensorReading
from app.sun.calculator import SunPosition
from app.weather.schema import WeatherSnapshot

Urgency = Literal["green", "amber", "red"]
ScenarioTag = str  # free-form tag composed by combine()
Actuator = str  # "blind:<group>" or "window:<zone>"

ZONES = ("mezzanine", "downstairs", "ceiling_apex", "bedroom")
BLIND_GROUPS = ("mezz", "downstairs", "bedroom")
WINDOW_ZONES = ZONES  # all four can be opened


@dataclass(frozen=True)
class Snapshot:
    now: datetime
    zones: dict[str, ZoneSensorReading]
    weather: WeatherSnapshot | None
    sun: SunPosition
    config: ConfigV1
    sw_lux: float | None = None  # single SW-glazing light reading (Phase 2: Aqara T1)
    current_blind: dict[str, int] = field(default_factory=dict)  # group → 0..100
    current_window: dict[str, bool] = field(default_factory=dict)  # zone → True/False


# --- Facts (output of classifier) -----------------------------------------------------------

ThermalLabel = Literal["cold", "comfortable", "hot"]
OutdoorLabel = Literal["cold_out", "mild_out", "hot_out"]
SkyLabel = Literal["sunny", "partly", "cloudy"]
WindLabel = Literal["still", "breeze", "windy"]
PhaseLabel = Literal["pre_dawn", "morning", "midday", "afternoon", "evening", "post_sunset", "night"]
SolarLoadLabel = Literal["low", "moderate", "high"]


@dataclass(frozen=True)
class Facts:
    now: datetime
    zone_thermal: dict[str, ThermalLabel]
    zone_temp: dict[str, float]
    zone_humidity: dict[str, float | None]
    zone_apparent: dict[str, float]
    zone_lux: dict[str, float | None]
    outdoor: OutdoorLabel | None
    sky: SkyLabel | None
    wind: WindLabel | None
    phase: PhaseLabel
    sun_on_sw: bool
    solar_load: SolarLoadLabel | None
    bedtime_window: bool
    precip: bool
    weather: WeatherSnapshot | None
    config: ConfigV1
    house_avg_temp: float
    apex_excess_c: float  # apex_temp - house_avg
    forecast_max_c: float | None  # max temp_c in next 12h
    sunset: datetime
    sunrise: datetime


# --- Rule output ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleOutput:
    rule: str
    priority: int
    blind_targets: dict[str, int] = field(default_factory=dict)  # group -> blind_pct (0..100)
    window_targets: dict[str, bool] = field(default_factory=dict)  # zone -> open
    urgency: Urgency = "green"
    scenario: str = ""
    reasoning: str = ""


# --- Final dashboard recommendation --------------------------------------------------------


@dataclass(frozen=True)
class BlindGroupRecommendation:
    group: str
    blind_pct: int
    urgency: Urgency
    scenario: str
    reasons: list[str]


@dataclass(frozen=True)
class ZoneWindowRecommendation:
    zone: str
    window_open: bool | None  # None = no recommendation (no rule fired)
    urgency: Urgency
    scenario: str
    reasons: list[str]


@dataclass(frozen=True)
class GlobalSummary:
    scenario: str
    urgency: Urgency


@dataclass(frozen=True)
class DashboardRecommendation:
    ts: datetime
    by_blind_group: dict[str, BlindGroupRecommendation]
    by_zone: dict[str, ZoneWindowRecommendation]
    global_: GlobalSummary
    prompts: list[str]
    rule_errors: list[str]
