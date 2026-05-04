from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import azimuth, elevation, sunrise, sunset

from app.config.schema import ConfigV1


@dataclass(frozen=True)
class SunPosition:
    elevation_deg: float
    azimuth_deg: float
    sunrise: datetime
    sunset: datetime
    is_daylight: bool


def compute(now: datetime, cfg: ConfigV1) -> SunPosition:
    loc = LocationInfo(
        name="loft",
        region="local",
        timezone=cfg.location.timezone,
        latitude=cfg.location.latitude,
        longitude=cfg.location.longitude,
    )
    tz = ZoneInfo(cfg.location.timezone)
    now_local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    elev = elevation(loc.observer, now_local)
    az = azimuth(loc.observer, now_local)
    sr = sunrise(loc.observer, date=now_local.date(), tzinfo=tz)
    ss = sunset(loc.observer, date=now_local.date(), tzinfo=tz)
    return SunPosition(
        elevation_deg=float(elev),
        azimuth_deg=float(az),
        sunrise=sr,
        sunset=ss,
        is_daylight=elev > 0,
    )


def is_sun_on_sw(pos: SunPosition, cfg: ConfigV1, lux_indoor: float | None = None) -> bool:
    """Astronomical predicate, optionally confirmed (logical OR) by indoor lux."""
    sw = cfg.sun_on_sw
    geometric = (
        sw.azimuth_min_deg <= pos.azimuth_deg <= sw.azimuth_max_deg
        and pos.elevation_deg > sw.elevation_min_deg
    )
    if geometric:
        return True
    # Below the horizon (or far off azimuth): never count as on-SW even if a lamp glares.
    if not pos.is_daylight:
        return False
    # Daylight, geometry borderline — confirm via direct-beam lux threshold.
    if lux_indoor is not None and lux_indoor >= sw.lux_indoor_direct_threshold:
        # Only confirm if azimuth is at least loosely SW-facing.
        if (sw.azimuth_min_deg - 30) <= pos.azimuth_deg <= (sw.azimuth_max_deg + 30):
            return True
    return False
