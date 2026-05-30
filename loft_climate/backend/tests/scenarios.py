"""Named scenario builders for engine matrix tests.

Each function returns a Snapshot ready for engine.decide(). Test-only
since v0.6.0 — the production /api/simulate route was removed when the
Simulate UI was deleted. Living here keeps test coverage of the engine
matrix without shipping fixture code in the production image.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config.schema import ConfigV1
from app.engine.types import Snapshot
from app.sensors.source import ZoneSensorReading
from app.sun.calculator import SunPosition
from app.weather.schema import HourlyForecast, WeatherSnapshot

# Helper builders ----------------------------------------------------------------


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    # Use UTC timestamps that are compatible with London local in summer (BST = UTC+1).
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _zone(zone: str, temp: float, humid: float = 50, lux: float | None = None) -> ZoneSensorReading:
    # `lux` arg retained for legacy scenarios but no longer used by the engine
    # (sw_lux is now the single SW-glazing reading on Snapshot).
    return ZoneSensorReading(
        zone=zone,
        ts=_ts(2026, 7, 15, 14),
        temp_c=temp,
        humidity_pct=humid,
        lux_indoor=lux,
    )


def _sun(
    elev: float,
    az: float,
    sunrise_hour: int = 5,
    sunset_hour: int = 21,
    on: datetime | None = None,
) -> SunPosition:
    base = on or _ts(2026, 7, 15, 0)
    base_midnight = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return SunPosition(
        elevation_deg=elev,
        azimuth_deg=az,
        sunrise=base_midnight.replace(hour=sunrise_hour),
        sunset=base_midnight.replace(hour=sunset_hour),
        is_daylight=elev > 0,
    )


def _weather(
    temp: float,
    feels: float | None = None,
    cloud: float = 10,
    wind: float = 4.0,
    uvi: float = 6.0,
    conditions: str = "Clear",
    precip: bool = False,
    forecast_max_temp: float | None = None,
) -> WeatherSnapshot:
    fetched = _ts(2026, 7, 15, 14)
    sunrise = fetched.replace(hour=5, minute=0)
    sunset = fetched.replace(hour=21, minute=0)
    forecast_temp = forecast_max_temp if forecast_max_temp is not None else max(temp, 22)
    hourly = [
        HourlyForecast(
            ts=fetched + timedelta(hours=i),
            temp_c=forecast_temp if i == 3 else temp,
            feels_like_c=feels if feels is not None else (forecast_temp if i == 3 else temp),
            humidity_pct=55,
            cloud_cover_pct=cloud,
            wind_speed_mps=wind,
            uvi=uvi,
            pop=0.5 if precip else 0.0,
        )
        for i in range(12)
    ]
    return WeatherSnapshot(
        fetched_at=fetched,
        temp_c=temp,
        feels_like_c=feels if feels is not None else temp,
        humidity_pct=55,
        cloud_cover_pct=cloud,
        wind_speed_mps=wind,
        wind_gust_mps=None,
        uvi=uvi,
        conditions=conditions,
        precip_now=precip,
        sunrise=sunrise,
        sunset=sunset,
        hourly=hourly,
    )


def _zones_uniform(temp: float, humid: float = 50, lux: float | None = None) -> dict[str, ZoneSensorReading]:
    return {
        z: _zone(z, temp, humid, lux)
        for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")
    }


# Scenarios ----------------------------------------------------------------------


def hot_sunny_breeze(cfg: ConfigV1) -> Snapshot:
    # Indoor warmer than outdoor (heat already trapped); outdoor still classed hot but breezy.
    return Snapshot(
        now=_ts(2026, 7, 15, 14),
        zones=_zones_uniform(temp=26.0, humid=50),
        weather=_weather(temp=23.0, feels=24.0, cloud=10, wind=5.0, uvi=8.0,
                         forecast_max_temp=27.0),
        sun=_sun(elev=45, az=220),
        config=cfg,
        sw_lux=12000,
    )


def hot_sunny_still(cfg: ConfigV1) -> Snapshot:
    return Snapshot(
        now=_ts(2026, 7, 15, 14),
        zones=_zones_uniform(temp=24.0, humid=50),
        weather=_weather(temp=28.0, feels=29.0, cloud=10, wind=0.5, uvi=8.0),
        sun=_sun(elev=45, az=220),
        config=cfg,
        sw_lux=12000,
    )


def hot_cloudy(cfg: ConfigV1) -> Snapshot:
    return Snapshot(
        now=_ts(2026, 7, 15, 14),
        zones=_zones_uniform(temp=24.0, humid=55),
        weather=_weather(temp=23.0, feels=24.0, cloud=85, wind=4.0, uvi=2.0, conditions="Clouds"),
        sun=_sun(elev=40, az=220),
        config=cfg,
        sw_lux=400,
    )


def cold_sunny(cfg: ConfigV1) -> Snapshot:
    # Indoor cold (<19) so harvest_solar fires.
    now = _ts(2026, 1, 15, 11)
    cold_zones = _zones_uniform(temp=18.0, humid=45)
    return Snapshot(
        now=now,
        zones=cold_zones,
        weather=_weather(temp=8.0, feels=6.0, cloud=10, wind=2.0, uvi=2.0),
        sun=_sun(elev=20, az=200, sunrise_hour=8, sunset_hour=16, on=now),
        config=cfg,
        sw_lux=9000,
    )


def cold_cloudy(cfg: ConfigV1) -> Snapshot:
    # January cloud cover. Sun elevation below the elevation_min threshold
    # for "on glazing" — winter sun barely peeking, low enough that even
    # the v0.11 lowered threshold (5°) excludes it.
    now = _ts(2026, 1, 15, 11)
    return Snapshot(
        now=now,
        zones=_zones_uniform(temp=18.0, humid=55),
        weather=_weather(temp=4.0, feels=2.0, cloud=90, wind=3.0, uvi=0.5, conditions="Clouds"),
        sun=_sun(elev=3, az=200, sunrise_hour=8, sunset_hour=16, on=now),
        config=cfg,
        sw_lux=200,
    )


def post_sunset_purge(cfg: ConfigV1) -> Snapshot:
    """Hot indoor, cool outdoor breeze, after sunset."""
    return Snapshot(
        now=_ts(2026, 7, 15, 21),
        zones=_zones_uniform(temp=26.0, humid=55),
        weather=_weather(temp=18.0, feels=18.0, cloud=20, wind=3.0, uvi=0.0, conditions="Clear"),
        sun=_sun(elev=-3, az=290),
        config=cfg,
        sw_lux=50,
    )


def pre_dawn_pre_cool(cfg: ConfigV1) -> Snapshot:
    """Pre-dawn, hot day forecast (~03:30 BST)."""
    return Snapshot(
        now=_ts(2026, 7, 15, 2, 30),
        zones=_zones_uniform(temp=22.0, humid=60),
        weather=_weather(
            temp=15.0, feels=15.0, cloud=10, wind=2.0, uvi=0.0,
            conditions="Clear", forecast_max_temp=29.0,
        ),
        sun=_sun(elev=-5, az=60),
        config=cfg,
        sw_lux=0,
    )


def bedtime_too_warm(cfg: ConfigV1) -> Snapshot:
    """21:30 local, bedroom warm."""
    z = {
        "mezzanine":    _zone("mezzanine", 23.0, 55),
        "downstairs":   _zone("downstairs", 22.0, 55),
        "ceiling_apex": _zone("ceiling_apex", 24.0, 55),
        "bedroom":      _zone("bedroom", 23.5, 55),
    }
    return Snapshot(
        now=_ts(2026, 7, 15, 20, 30),  # 21:30 BST local = 20:30 UTC
        zones=z,
        weather=_weather(temp=18.0, feels=18.0, cloud=20, wind=2.0, uvi=0.0, conditions="Clear"),
        sun=_sun(elev=2, az=290),
        config=cfg,
        sw_lux=0,
    )


def bedroom_overheat_safety(cfg: ConfigV1) -> Snapshot:
    z = {
        "mezzanine":    _zone("mezzanine", 26.0, 55),
        "downstairs":   _zone("downstairs", 25.0, 55),
        "ceiling_apex": _zone("ceiling_apex", 27.0, 55),
        "bedroom":      _zone("bedroom", 26.5, 60),
    }
    return Snapshot(
        now=_ts(2026, 7, 15, 21, 0),  # 22:00 BST
        zones=z,
        weather=_weather(temp=18.0, feels=18.0, cloud=20, wind=1.0, uvi=0.0, conditions="Clear"),
        sun=_sun(elev=-2, az=290),
        config=cfg,
        sw_lux=0,
    )


def apex_stratification(cfg: ConfigV1) -> Snapshot:
    z = {
        "mezzanine":    _zone("mezzanine", 22.0, 50),
        "downstairs":   _zone("downstairs", 21.0, 50),
        "ceiling_apex": _zone("ceiling_apex", 27.5, 45),
        "bedroom":      _zone("bedroom", 22.0, 50),
    }
    return Snapshot(
        now=_ts(2026, 7, 15, 16),
        zones=z,
        weather=_weather(temp=20.0, feels=20.0, cloud=40, wind=2.0, uvi=4.0, conditions="Clouds"),
        sun=_sun(elev=30, az=240),
        config=cfg,
        sw_lux=0,
    )


def mild_outdoor_warm_indoor(cfg: ConfigV1) -> Snapshot:
    """Cool-cloudy May day, indoor heated up to 23°C — should vent."""
    now = _ts(2026, 5, 2, 14)
    return Snapshot(
        now=now,
        zones=_zones_uniform(temp=23.0, humid=55),
        weather=_weather(
            temp=13.7, feels=13.2, cloud=100, wind=2.6, uvi=0.5,
            conditions="Clouds", forecast_max_temp=14.5,
        ),
        sun=_sun(elev=34, az=110, sunrise_hour=5, sunset_hour=20, on=now),
        config=cfg,
        sw_lux=600,
    )


def rain_override(cfg: ConfigV1) -> Snapshot:
    return Snapshot(
        now=_ts(2026, 7, 15, 14),
        zones=_zones_uniform(temp=24.0, humid=70),
        weather=_weather(
            temp=22.0, feels=23.0, cloud=90, wind=5.0, uvi=2.0,
            conditions="Rain", precip=True,
        ),
        sun=_sun(elev=40, az=220),
        config=cfg,
        sw_lux=2000,
    )


SCENARIOS = {
    "hot_sunny_breeze": hot_sunny_breeze,
    "hot_sunny_still": hot_sunny_still,
    "hot_cloudy": hot_cloudy,
    "cold_sunny": cold_sunny,
    "cold_cloudy": cold_cloudy,
    "mild_outdoor_warm_indoor": mild_outdoor_warm_indoor,
    "post_sunset_purge": post_sunset_purge,
    "pre_dawn_pre_cool": pre_dawn_pre_cool,
    "bedtime_too_warm": bedtime_too_warm,
    "bedroom_overheat_safety": bedroom_overheat_safety,
    "apex_stratification": apex_stratification,
    "rain_override": rain_override,
}
