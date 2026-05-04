from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api._serialise import serialise_weather
from app.config.loader import load_config
from app.db.session import get_session
from app.weather import cache as weather_cache
from app.weather.client import OWM30AccessError

router = APIRouter(prefix="/api/weather", tags=["weather"])


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
