from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.weather.schema import HourlyForecast, WeatherSnapshot

OWM_BASE = "https://api.openweathermap.org/data/3.0/onecall"


class OWM30AccessError(RuntimeError):
    """Raised when the API key lacks One Call 3.0 access."""


def _to_dt(unix: int | float) -> datetime:
    return datetime.fromtimestamp(int(unix), tz=timezone.utc)


def _parse(payload: dict) -> WeatherSnapshot:
    cur = payload.get("current") or {}
    weather_arr = cur.get("weather") or [{}]
    conditions = (weather_arr[0].get("main") or "Unknown") if weather_arr else "Unknown"
    rain_now = bool(cur.get("rain"))
    snow_now = bool(cur.get("snow"))

    hourly_raw = payload.get("hourly") or []
    hourly: list[HourlyForecast] = []
    for h in hourly_raw[:24]:
        hourly.append(
            HourlyForecast(
                ts=_to_dt(h.get("dt", 0)),
                temp_c=float(h.get("temp", 0.0)),
                feels_like_c=float(h.get("feels_like", h.get("temp", 0.0))),
                humidity_pct=float(h.get("humidity", 0)),
                cloud_cover_pct=float(h.get("clouds", 0)),
                wind_speed_mps=float(h.get("wind_speed", 0.0)),
                uvi=float(h.get("uvi", 0.0)),
                pop=float(h.get("pop", 0.0)),
            )
        )

    return WeatherSnapshot(
        fetched_at=datetime.now(tz=timezone.utc),
        temp_c=float(cur.get("temp", 0.0)),
        feels_like_c=float(cur.get("feels_like", cur.get("temp", 0.0))),
        humidity_pct=float(cur.get("humidity", 0)),
        cloud_cover_pct=float(cur.get("clouds", 0)),
        wind_speed_mps=float(cur.get("wind_speed", 0.0)),
        wind_gust_mps=float(cur["wind_gust"]) if "wind_gust" in cur else None,
        uvi=float(cur.get("uvi", 0.0)),
        conditions=conditions,
        precip_now=rain_now or snow_now,
        sunrise=_to_dt(cur.get("sunrise", 0)),
        sunset=_to_dt(cur.get("sunset", 0)),
        hourly=hourly,
        stale=False,
    )


async def fetch(api_key: str, lat: float, lon: float) -> WeatherSnapshot:
    if not api_key:
        raise OWM30AccessError(
            "OWM_API_KEY not set. Subscribe to One Call 3.0 at "
            "https://openweathermap.org/api/one-call-3 then put the key in .env."
        )
    params = {
        "lat": f"{lat}",
        "lon": f"{lon}",
        "appid": api_key,
        "units": "metric",
        "exclude": "minutely,daily,alerts",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OWM_BASE, params=params)
    if resp.status_code in (401, 403):
        raise OWM30AccessError(
            "OpenWeatherMap returned "
            f"{resp.status_code}. Your API key probably lacks One Call 3.0 access. "
            "Subscribe at https://openweathermap.org/api/one-call-3 (free tier: 1000 calls/day)."
        )
    resp.raise_for_status()
    return _parse(resp.json())
