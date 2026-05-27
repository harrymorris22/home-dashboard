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


def is_sun_on_sw(
    pos: SunPosition,
    cfg: ConfigV1,
    lux_indoor: float | None = None,
    sw_blinds_blocking: bool = False,
) -> bool:
    """Astronomical predicate, optionally confirmed (logical OR) by indoor lux.

    ``sw_blinds_blocking`` (v0.10): when the SW-window blinds are physically
    down, the indoor lux sensor sits *behind* them and can't see whether sun
    is hitting the glazing from outside. A low reading no longer means "no
    sun" — it means "no visibility". Without this flag, the engine
    whiplashes: blinds down → low lux → "no sun" → "blinds up" → blinds
    open → sun pours in → "block solar gain" → "blinds down" → repeat.

    When the flag is True we skip the lux fallback entirely and use a wider
    geometric heuristic instead. Conservative bias: when in doubt during
    daylight + loosely-SW azimuth, assume sun IS on SW and let downstream
    rules (which require solar_load=high to actually block) decide.
    """
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

    # Loose-SW envelope used by both the lux-confirmation and blinds-blocking
    # branches below. ±30° widens the strict geometric window to catch sun
    # angles where direct-beam light is still arriving on the glazing.
    loose_sw = (
        (sw.azimuth_min_deg - 30) <= pos.azimuth_deg <= (sw.azimuth_max_deg + 30)
    )

    if sw_blinds_blocking:
        # Lux is meaningless — blinds block the sensor's view to the outside.
        # Fall back to widened geometry. Be conservative: assume sun on SW
        # when loosely SW-facing in daylight (safer to keep blinds down than
        # open them on a false negative).
        return loose_sw

    # Blinds aren't blocking — use lux to confirm borderline geometry.
    if lux_indoor is not None and lux_indoor >= sw.lux_indoor_direct_threshold:
        if loose_sw:
            return True
    return False
