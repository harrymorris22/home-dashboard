from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api._serialise import serialise_recommendation, serialise_weather
from app.db.session import get_session
from app.snapshot.service import build_full_state

router = APIRouter(prefix="/api", tags=["state"])


@router.get("/state")
async def get_state(request: Request, session: Session = Depends(get_session)):
    ha_client = getattr(request.app.state, "ha_client", None)
    bundle = await build_full_state(session, ha_client)
    snap = bundle.snap
    rec = bundle.rec

    sensors_out = {}
    now_utc = datetime.now(tz=timezone.utc)
    for zone, r in snap.zones.items():
        sensors_out[zone] = {
            "temp_c": r.temp_c,
            "humidity_pct": r.humidity_pct,
            "lux_indoor": r.lux_indoor,
            "ts": r.ts.isoformat(),
            "age_seconds": (
                now_utc - (r.ts if r.ts.tzinfo else r.ts.replace(tzinfo=timezone.utc))
            ).total_seconds(),
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
        # v0.21: outdoor breakdown — three temperatures side-by-side so the
        # dashboard can show what each source says.
        #   effective_c   → the value the rules see (== weather.temp_c)
        #   raw_c         → SwitchBot sensor before any correction (None when
        #                   no outdoor sensor is configured)
        #   forecast_c    → Met.no's own reading (None when weather is offline)
        #   delta_c       → effective_c − raw_c, the correction applied
        "outdoor": {
            "effective_c": (
                snap.weather.temp_c if snap.weather is not None else None
            ),
            "raw_c": snap.outdoor_raw_c,
            "forecast_c": snap.outdoor_forecast_c,
            "delta_c": (
                snap.weather.temp_c - snap.outdoor_raw_c
                if snap.weather is not None and snap.outdoor_raw_c is not None
                else None
            ),
        },
        "current_state": {
            "blinds": dict(snap.current_blind),
            "windows": dict(snap.current_window),
        },
        "recommendations": serialise_recommendation(rec),
        "next_actions": bundle.next_actions,
    }
