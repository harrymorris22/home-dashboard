from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config.schema import ConfigV1
from app.engine.heat_index import apparent_temp_c
from app.engine.types import (
    Facts,
    OutdoorLabel,
    PhaseLabel,
    SkyLabel,
    SolarLoadLabel,
    ThermalLabel,
    WindLabel,
)
from app.sensors.source import ZoneSensorReading
from app.sun.calculator import SunPosition, is_sun_on_sw
from app.weather.schema import WeatherSnapshot


def classify_zone_thermal(t_app: float, comfort_min: float, comfort_max: float) -> ThermalLabel:
    if t_app < comfort_min:
        return "cold"
    if t_app > comfort_max:
        return "hot"
    return "comfortable"


def classify_outdoor(weather: WeatherSnapshot | None, cfg: ConfigV1) -> OutdoorLabel | None:
    if weather is None:
        return None
    feels = weather.feels_like_c
    if feels >= cfg.thermal.outdoor_hot_c:
        return "hot_out"
    if feels <= cfg.thermal.outdoor_cold_c:
        return "cold_out"
    return "mild_out"


def classify_sky(weather: WeatherSnapshot | None, cfg: ConfigV1) -> SkyLabel | None:
    if weather is None:
        return None
    cc = weather.cloud_cover_pct
    if cc <= cfg.sky.sunny_max_cloud_pct:
        return "sunny"
    if cc >= cfg.sky.cloudy_min_cloud_pct:
        return "cloudy"
    return "partly"


def classify_wind(weather: WeatherSnapshot | None, cfg: ConfigV1) -> WindLabel | None:
    if weather is None:
        return None
    w = weather.wind_speed_mps
    if w < cfg.wind.still_max_mps:
        return "still"
    if w >= cfg.wind.breeze_min_mps:
        # Cap "windy" at a reasonable threshold; the matrix only needs still/breeze.
        return "windy" if w >= 8.0 else "breeze"
    return "still"  # gap between still_max and breeze_min defaults to still side


def classify_phase(now: datetime, sun: SunPosition, cfg: ConfigV1) -> PhaseLabel:
    tz = ZoneInfo(cfg.location.timezone)
    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    h = local.hour
    sunrise_local = sun.sunrise.astimezone(tz)
    sunset_local = sun.sunset.astimezone(tz)
    if local < sunrise_local - timedelta(hours=1):
        return "pre_dawn"
    if local < sunrise_local + timedelta(hours=2):
        return "morning"
    if local < sunset_local - timedelta(hours=4):
        return "midday"
    if local < sunset_local:
        return "afternoon"
    if local < sunset_local + timedelta(hours=2):
        return "post_sunset"
    if h >= 22 or h < 5:
        return "night"
    return "evening"


def classify_solar_load(weather: WeatherSnapshot | None, cfg: ConfigV1) -> SolarLoadLabel | None:
    if weather is None:
        return None
    uvi = weather.uvi
    cc = weather.cloud_cover_pct
    if uvi >= cfg.solar.uvi_high and cc <= 50:
        return "high"
    if uvi >= cfg.solar.uvi_moderate:
        return "moderate"
    return "low"


def classify_bedtime_window(now: datetime, cfg: ConfigV1) -> bool:
    """True when within bedtime_prep_minutes BEFORE bedtime_local."""
    bedroom = cfg.zones.get("bedroom")
    if bedroom is None or bedroom.bedtime_prep_minutes is None:
        return False
    tz = ZoneInfo(cfg.location.timezone)
    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    h, m = cfg.schedule.bedtime_local.split(":")
    bedtime = local.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if bedtime < local:
        bedtime += timedelta(days=1)
    delta = bedtime - local
    return timedelta(0) < delta <= timedelta(minutes=bedroom.bedtime_prep_minutes)


def classify_precip(weather: WeatherSnapshot | None) -> bool:
    if weather is None:
        return False
    if weather.precip_now:
        return True
    bad = {"Rain", "Drizzle", "Thunderstorm", "Snow"}
    return weather.conditions in bad


def _forecast_max(weather: WeatherSnapshot | None, hours: int = 12) -> float | None:
    if weather is None or not weather.hourly:
        return None
    sliced = weather.hourly[: max(1, hours)]
    return max(h.temp_c for h in sliced)


def build_facts(
    now: datetime,
    zones: dict[str, ZoneSensorReading],
    weather: WeatherSnapshot | None,
    sun: SunPosition,
    cfg: ConfigV1,
    sw_lux: float | None = None,
    current_blind: dict[str, int] | None = None,
) -> Facts:
    zone_thermal: dict[str, ThermalLabel] = {}
    zone_apparent: dict[str, float] = {}
    zone_temp: dict[str, float] = {}
    zone_humidity: dict[str, float | None] = {}
    zone_lux: dict[str, float | None] = {}
    for zone_id, zcfg in cfg.zones.items():
        r = zones.get(zone_id)
        if r is None:
            continue
        t_app = apparent_temp_c(r.temp_c, r.humidity_pct)
        zone_apparent[zone_id] = t_app
        zone_temp[zone_id] = r.temp_c
        zone_humidity[zone_id] = r.humidity_pct
        zone_lux[zone_id] = r.lux_indoor
        zone_thermal[zone_id] = classify_zone_thermal(t_app, zcfg.comfort_min, zcfg.comfort_max)

    house_avg = (
        sum(zone_temp.values()) / len(zone_temp) if zone_temp else 0.0
    )
    apex_temp = zone_temp.get("ceiling_apex", house_avg)
    apex_excess = apex_temp - house_avg

    # Sun-on-SW lux confirmation: prefer the dedicated SW glazing reading; fall back to
    # any per-zone lux if a legacy caller provides only that.
    confirm_lux: float | None = sw_lux
    if confirm_lux is None:
        for zid in ("mezzanine", "downstairs", "bedroom"):
            v = zone_lux.get(zid)
            if v is not None:
                confirm_lux = v if confirm_lux is None else max(confirm_lux, v)

    # The Aqara T1 lux sensor sits inside the SW window in the office (mezz
    # zone). When mezz blinds are physically down (>= 75%), the sensor's view
    # to the outside is blocked — its reading can't tell us whether sun is
    # actually on the glazing. Tell is_sun_on_sw to skip lux confirmation in
    # that case so we don't loop "blinds down → low lux → blinds up → sun
    # pours in → blinds down".
    cb = current_blind or {}
    sw_blinds_blocking = cb.get("mezz", 0) >= 75
    sun_on_sw = is_sun_on_sw(sun, cfg, confirm_lux, sw_blinds_blocking=sw_blinds_blocking)

    return Facts(
        now=now,
        zone_thermal=zone_thermal,
        zone_temp=zone_temp,
        zone_humidity=zone_humidity,
        zone_apparent=zone_apparent,
        zone_lux=zone_lux,
        outdoor=classify_outdoor(weather, cfg),
        sky=classify_sky(weather, cfg),
        wind=classify_wind(weather, cfg),
        phase=classify_phase(now, sun, cfg),
        sun_on_sw=sun_on_sw,
        solar_load=classify_solar_load(weather, cfg),
        bedtime_window=classify_bedtime_window(now, cfg),
        precip=classify_precip(weather),
        weather=weather,
        config=cfg,
        house_avg_temp=house_avg,
        apex_excess_c=apex_excess,
        forecast_max_c=_forecast_max(weather, hours=12),
        sunset=sun.sunset,
        sunrise=sun.sunrise,
    )
