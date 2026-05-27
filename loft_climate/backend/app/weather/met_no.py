"""Met.no LocationForecast 2.0 adapter.

The Norwegian Meteorological Institute publishes a free public weather API
with no key, no registration, no rate limit, just a polite ``User-Agent``
header. Forecast quality for the UK is excellent because the response
blends UK Met Office data alongside Met.no's own model.

Endpoint: ``https://api.met.no/weatherapi/locationforecast/2.0/complete``

Why ``complete`` and not ``compact``: compact omits
``probability_of_precipitation`` which the engine's forecast projector uses
to decide whether window-open windows are about to get rained on. complete
is the same shape plus this field, same caching, same response size class.

Sunrise/sunset are NOT returned by LocationForecast. We compute them with
``astral`` (already a dependency for ``app.sun.calculator``). One less
network call, deterministic on Pi.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from astral import LocationInfo
from astral.sun import sunrise, sunset

from app.weather.schema import HourlyForecast, WeatherSnapshot

MET_NO_BASE = "https://api.met.no/weatherapi/locationforecast/2.0/complete"


class MetNoError(RuntimeError):
    """Raised on a non-success Met.no response."""


# Met.no's symbol_code → human-readable categorical label. Same vocabulary
# the engine's classifier already uses: "Clear", "Clouds", "Rain", "Snow",
# "Drizzle", "Thunderstorm", "Fog". Pre-v0.7 the engine read OWM's `main`
# string. We keep the same vocabulary so engine code is unchanged.
#
# Met.no codes (https://api.met.no/weatherapi/weathericon/2.0/documentation):
#   clearsky, fair, partlycloudy, cloudy, fog,
#   rainshowers, lightrainshowers, heavyrainshowers,
#   rain, lightrain, heavyrain,
#   sleet, sleetshowers, lightsleet, heavysleet,
#   snow, snowshowers, lightsnow, heavysnow,
#   rainshowersandthunder, rainandthunder, sleetandthunder, snowandthunder,
#   ... each with optional _day / _night suffix
def _conditions_from_symbol(symbol: str | None) -> str:
    if not symbol:
        return "Unknown"
    # Strip _day / _night / _polartwilight suffix.
    base = symbol.replace("_day", "").replace("_night", "").replace("_polartwilight", "")
    if "thunder" in base:
        return "Thunderstorm"
    if "snow" in base or "sleet" in base:
        return "Snow"
    if "rain" in base or "drizzle" in base:
        return "Rain"
    if "fog" in base:
        return "Fog"
    if "cloud" in base:
        return "Clouds"
    if "fair" in base or "clear" in base:
        return "Clear"
    return base.capitalize()


def _effective_uvi(clear_sky_uvi: float, cloud_cover_pct: float) -> float:
    """Met.no reports UV index assuming a clear sky. The engine uses UV as a
    solar-load proxy alongside cloud cover, so we attenuate it by ~80% of the
    cloud fraction (clouds block roughly 0–95% of UV depending on type; 80%
    is a defensible average for thick stratus). Without this, we'd over-fire
    the "high solar load" rules on cloudy days.
    """
    attenuation = 1.0 - 0.8 * (cloud_cover_pct / 100.0)
    return max(0.0, clear_sky_uvi * attenuation)


def _astral_sunrise_sunset(lat: float, lon: float, now: datetime) -> tuple[datetime, datetime]:
    loc = LocationInfo(name="loft", region="local", timezone="UTC", latitude=lat, longitude=lon)
    today = now.date()
    sr = sunrise(loc.observer, date=today, tzinfo=timezone.utc)
    ss = sunset(loc.observer, date=today, tzinfo=timezone.utc)
    return sr, ss


def _hourly_from_timeseries(timeseries: list[dict[str, Any]]) -> list[HourlyForecast]:
    out: list[HourlyForecast] = []
    for entry in timeseries[:24]:
        ts_raw = entry.get("time")
        if not ts_raw:
            continue
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        data = entry.get("data") or {}
        instant = (data.get("instant") or {}).get("details") or {}
        next_1h = data.get("next_1_hours") or {}
        next_1h_details = next_1h.get("details") or {}

        temp_c = float(instant.get("air_temperature", 0.0))
        humidity_pct = float(instant.get("relative_humidity", 0.0))
        cloud_pct = float(instant.get("cloud_area_fraction", 0.0))
        wind_speed = float(instant.get("wind_speed", 0.0))
        clear_uvi = float(instant.get("ultraviolet_index_clear_sky", 0.0))
        uvi = _effective_uvi(clear_uvi, cloud_pct)
        # pop is reported as 0..100 by Met.no, we store 0..1.
        pop = float(next_1h_details.get("probability_of_precipitation", 0.0)) / 100.0

        out.append(
            HourlyForecast(
                ts=ts,
                temp_c=temp_c,
                feels_like_c=temp_c,  # Met.no doesn't expose feels-like; classifier reads temp_c primarily
                humidity_pct=humidity_pct,
                cloud_cover_pct=cloud_pct,
                wind_speed_mps=wind_speed,
                uvi=uvi,
                pop=pop,
            )
        )
    return out


def _parse(payload: dict[str, Any], lat: float, lon: float) -> WeatherSnapshot:
    props = payload.get("properties") or {}
    timeseries = props.get("timeseries") or []
    if not timeseries:
        raise MetNoError("Met.no response had no timeseries entries.")

    current = timeseries[0]
    cur_data = current.get("data") or {}
    instant = (cur_data.get("instant") or {}).get("details") or {}
    next_1h = cur_data.get("next_1_hours") or {}
    next_1h_summary = next_1h.get("summary") or {}
    next_1h_details = next_1h.get("details") or {}

    temp_c = float(instant.get("air_temperature", 0.0))
    cloud_pct = float(instant.get("cloud_area_fraction", 0.0))
    humidity_pct = float(instant.get("relative_humidity", 0.0))
    wind_speed = float(instant.get("wind_speed", 0.0))
    wind_gust = instant.get("wind_speed_of_gust")
    clear_uvi = float(instant.get("ultraviolet_index_clear_sky", 0.0))
    uvi = _effective_uvi(clear_uvi, cloud_pct)

    conditions = _conditions_from_symbol(next_1h_summary.get("symbol_code"))
    # precip_now: precipitation forecast > 0 in the next hour.
    precip_amount = float(next_1h_details.get("precipitation_amount", 0.0))
    precip_now = precip_amount > 0.0

    now = datetime.now(tz=timezone.utc)
    sr, ss = _astral_sunrise_sunset(lat, lon, now)
    hourly = _hourly_from_timeseries(timeseries)

    return WeatherSnapshot(
        fetched_at=now,
        temp_c=temp_c,
        feels_like_c=temp_c,
        humidity_pct=humidity_pct,
        cloud_cover_pct=cloud_pct,
        wind_speed_mps=wind_speed,
        wind_gust_mps=float(wind_gust) if wind_gust is not None else None,
        uvi=uvi,
        conditions=conditions,
        precip_now=precip_now,
        sunrise=sr,
        sunset=ss,
        hourly=hourly,
        stale=False,
    )


async def fetch(lat: float, lon: float, user_agent: str) -> WeatherSnapshot:
    """Fetch a forecast from Met.no.

    Met.no requires an identifiable ``User-Agent`` header so they can
    contact you if your client misbehaves. Format: ``MyApp/1.0 contact@example.com``.
    """
    if not user_agent or "@" not in user_agent:
        raise MetNoError(
            "Met.no requires a User-Agent containing a contact email. "
            "Set `weather_user_agent` in your Add-on options to something "
            "like 'loft-climate/0.8.0 your-email@example.com'."
        )
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    params = {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(MET_NO_BASE, params=params, headers=headers)
    if resp.status_code == 403:
        raise MetNoError(
            "Met.no returned 403. Your User-Agent was rejected as anonymous. "
            "Make sure `weather_user_agent` includes a real contact email."
        )
    resp.raise_for_status()
    return _parse(resp.json(), lat, lon)
