from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api._serialise import serialise_recommendation, serialise_weather
from app.config.loader import load_config
from app.db.session import get_session
from app.engine.engine import decide
from app.engine.forecast import project_actions
from app.sensors.composite import CompositeSensorSource
from app.sensors.homeassistant import (
    HomeAssistantOutdoorSource,
    HomeAssistantSensorSource,
    HomeAssistantSunshineSource,
)
from app.sensors.manual import (
    ManualActuatorStateSource,
    ManualSensorSource,
    ManualSunshineSource,
)
from app.settings import get_settings
from app.snapshot.builder import SnapshotBuilder

router = APIRouter(prefix="/api", tags=["state"])


def _build_sensor_source(session: Session, request: Request):
    """HA-backed when configured + connected; manual fallback for missing zones."""
    settings = get_settings()
    ha_client = getattr(request.app.state, "ha_client", None)
    manual = ManualSensorSource(session)
    if ha_client is not None and settings.ha_entity_map:
        ha = HomeAssistantSensorSource(ha_client, settings.ha_entity_map)
        return CompositeSensorSource(ha, manual)
    return manual


@router.get("/state")
async def get_state(request: Request, session: Session = Depends(get_session)):
    cfg = load_config()
    settings = get_settings()
    ha_client = getattr(request.app.state, "ha_client", None)
    outdoor_source = None
    if ha_client is not None and settings.ha_outdoor_entities:
        outdoor_source = HomeAssistantOutdoorSource(ha_client, settings.ha_outdoor_entities)
    # HA-backed sunshine when configured AND has a value; fall back to manual entry otherwise.
    sunshine_source = ManualSunshineSource(session)
    if ha_client is not None and settings.ha_sunshine_entity:
        ha_sun = HomeAssistantSunshineSource(ha_client, settings.ha_sunshine_entity)
        if ha_sun.latest() is not None:
            sunshine_source = ha_sun
    builder = SnapshotBuilder(
        session,
        _build_sensor_source(session, request),
        cfg,
        sunshine_source=sunshine_source,
        actuator_state_source=ManualActuatorStateSource(session),
        outdoor_source=outdoor_source,
    )
    snap = await builder.build()
    rec = decide(snap)
    next_actions = project_actions(snap)

    sensors_out = {}
    now_utc = datetime.now(tz=timezone.utc)
    for zone, r in snap.zones.items():
        sensors_out[zone] = {
            "temp_c": r.temp_c,
            "humidity_pct": r.humidity_pct,
            "lux_indoor": r.lux_indoor,
            "ts": r.ts.isoformat(),
            "age_seconds": (now_utc - (r.ts if r.ts.tzinfo else r.ts.replace(tzinfo=timezone.utc))).total_seconds(),
        }

    return {
        "ts": snap.now.isoformat(),
        "sensors": sensors_out,
        "weather": serialise_weather(snap.weather),
        "sun": {
            "elevation_deg": snap.sun.elevation_deg,
            "azimuth_deg": snap.sun.azimuth_deg,
            "sunrise": snap.sun.sunrise.isoformat(),
            "sunset": snap.sun.sunset.isoformat(),
            "is_daylight": snap.sun.is_daylight,
        },
        "sunshine": {"lux": snap.sw_lux} if snap.sw_lux is not None else None,
        "current_state": {
            "blinds": dict(snap.current_blind),
            "windows": dict(snap.current_window),
        },
        "recommendations": serialise_recommendation(rec),
        "next_actions": next_actions,
    }
