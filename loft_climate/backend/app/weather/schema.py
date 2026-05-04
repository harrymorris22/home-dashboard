from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HourlyForecast:
    ts: datetime
    temp_c: float
    feels_like_c: float
    humidity_pct: float
    cloud_cover_pct: float
    wind_speed_mps: float
    uvi: float
    pop: float  # probability of precipitation 0..1


@dataclass(frozen=True)
class WeatherSnapshot:
    fetched_at: datetime
    temp_c: float
    feels_like_c: float
    humidity_pct: float
    cloud_cover_pct: float
    wind_speed_mps: float
    wind_gust_mps: float | None
    uvi: float
    conditions: str
    precip_now: bool
    sunrise: datetime
    sunset: datetime
    hourly: list[HourlyForecast]
    stale: bool = False
