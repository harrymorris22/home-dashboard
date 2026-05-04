from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config.schema import ConfigV1
from app.db import repo
from app.db.models import WeatherCache
from app.settings import get_settings
from app.weather import client as owm_client
from app.weather.schema import HourlyForecast, WeatherSnapshot

log = logging.getLogger(__name__)


def _serialise(snap: WeatherSnapshot) -> str:
    payload = asdict(snap)
    payload["fetched_at"] = snap.fetched_at.isoformat()
    payload["sunrise"] = snap.sunrise.isoformat()
    payload["sunset"] = snap.sunset.isoformat()
    payload["hourly"] = [
        {**asdict(h), "ts": h.ts.isoformat()} for h in snap.hourly
    ]
    return json.dumps(payload)


def _deserialise(raw: str, *, stale: bool = False) -> WeatherSnapshot:
    data = json.loads(raw)
    hourly = [
        HourlyForecast(
            ts=datetime.fromisoformat(h["ts"]),
            temp_c=h["temp_c"],
            feels_like_c=h["feels_like_c"],
            humidity_pct=h["humidity_pct"],
            cloud_cover_pct=h["cloud_cover_pct"],
            wind_speed_mps=h["wind_speed_mps"],
            uvi=h["uvi"],
            pop=h["pop"],
        )
        for h in data.get("hourly", [])
    ]
    return WeatherSnapshot(
        fetched_at=datetime.fromisoformat(data["fetched_at"]),
        temp_c=data["temp_c"],
        feels_like_c=data["feels_like_c"],
        humidity_pct=data["humidity_pct"],
        cloud_cover_pct=data["cloud_cover_pct"],
        wind_speed_mps=data["wind_speed_mps"],
        wind_gust_mps=data.get("wind_gust_mps"),
        uvi=data["uvi"],
        conditions=data["conditions"],
        precip_now=data["precip_now"],
        sunrise=datetime.fromisoformat(data["sunrise"]),
        sunset=datetime.fromisoformat(data["sunset"]),
        hourly=hourly,
        stale=stale,
    )


async def get_or_fetch(session: Session, cfg: ConfigV1, *, force: bool = False) -> WeatherSnapshot | None:
    """Return weather, refetching if cache is older than fetch_interval_seconds.

    Returns None if API call fails on cold start (no cached row available).
    """
    settings = get_settings()
    row = repo.latest_weather_row(session)
    now = datetime.now(tz=timezone.utc)

    fresh = False
    if row is not None and not force:
        age = (now - row.fetched_at.replace(tzinfo=timezone.utc) if row.fetched_at.tzinfo is None else now - row.fetched_at).total_seconds()
        if age < cfg.weather.fetch_interval_seconds:
            fresh = True

    if fresh and row is not None:
        return _deserialise(row.payload_json, stale=False)

    try:
        snap = await owm_client.fetch(
            api_key=settings.owm_api_key,
            lat=cfg.location.latitude,
            lon=cfg.location.longitude,
        )
    except Exception as e:
        log.warning("OWM fetch failed: %s", e)
        if row is not None:
            return _deserialise(row.payload_json, stale=True)
        return None

    new_row = WeatherCache(fetched_at=snap.fetched_at, payload_json=_serialise(snap))
    repo.insert_weather(session, new_row)
    session.commit()
    return snap
