from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api._serialise import serialise_weather
from app.config.loader import load_config
from app.db import repo
from app.db.session import get_session
from app.weather import cache as weather_cache
from app.weather.client import OWM30AccessError

router = APIRouter(prefix="/api/weather", tags=["weather"])

# Cap history window at 90 days. Weather rows are ~1/10min = ~13k/90d, which
# comfortably fits in a browser JSON payload but is enough for months of
# sensor-vs-forecast bias analysis.
HISTORY_MAX_DAYS = 90


@router.get("/current")
async def get_current(session: Session = Depends(get_session)):
    cfg = load_config()
    snap = await weather_cache.get_or_fetch(session, cfg)
    return {"weather": serialise_weather(snap)}


@router.post("/refresh")
async def force_refresh(session: Session = Depends(get_session)):
    cfg = load_config()
    try:
        snap = await weather_cache.get_or_fetch(session, cfg, force=True)
    except OWM30AccessError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"weather": serialise_weather(snap)}


@router.get("/history")
def get_history(
    days: int = Query(default=7, ge=1, le=HISTORY_MAX_DAYS),
    session: Session = Depends(get_session),
):
    """Return every cached Met.no snapshot from the last N days.

    Each row is one fetch — the provider is polled roughly every 10 minutes
    (see ``cfg.weather.fetch_interval_seconds``), so 7 days ≈ 1000 rows,
    30 days ≈ 4300 rows. Payload is intentionally raw: the client aggregates
    to whatever bucket (hourly / daily) it needs. Fields mirror the
    ``/current`` payload's weather object minus the hourly forecast (which
    would blow up the response).

    Motivation: pair this with the SwitchBot outdoor sensor history from
    Home Assistant Recorder to compute a per-hour bias curve — the sensor
    is known to over-read on sunny mornings and we need to see how bad the
    delta is across weeks.
    """
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    rows = repo.weather_rows_range(session, start, end)
    points = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json)
        except (ValueError, TypeError):
            # Corrupt row — skip rather than fail the whole window.
            continue
        fetched = row.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        points.append(
            {
                "ts": fetched.isoformat(),
                "temp_c": payload.get("temp_c"),
                "feels_like_c": payload.get("feels_like_c"),
                "humidity_pct": payload.get("humidity_pct"),
                "cloud_cover_pct": payload.get("cloud_cover_pct"),
                "wind_speed_mps": payload.get("wind_speed_mps"),
                "uvi": payload.get("uvi"),
                "conditions": payload.get("conditions"),
                "precip_now": payload.get("precip_now"),
            }
        )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "count": len(points),
        "points": points,
    }
