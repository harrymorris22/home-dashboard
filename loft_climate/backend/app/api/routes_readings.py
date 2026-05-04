from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import repo
from app.db.models import ActuatorState, Feedback, Reading, Sunshine
from app.db.session import get_session

router = APIRouter(prefix="/api", tags=["readings"])

# 0–5 scale → indoor lux on SW glazing. Tuned for the Aqara T1 mounted inside
# double-glazing in Phase 2; rough but useful for Phase 1 validation.
SUNSHINE_SCALE_LUX: dict[int, float] = {
    0: 0,        # dark / pre-dawn
    1: 500,      # overcast
    2: 2000,     # bright overcast
    3: 5000,     # hazy sun
    4: 10000,    # strong sun
    5: 15000,    # direct beam
}

SUNSHINE_SCALE_LABELS: dict[int, str] = {
    0: "Dark",
    1: "Overcast",
    2: "Bright overcast",
    3: "Hazy sun",
    4: "Strong sun",
    5: "Direct beam",
}


class ZonePayload(BaseModel):
    temp_c: float
    humidity_pct: float | None = None
    lux_indoor: float | None = None  # legacy; will go away in Phase 2


class FeedbackPayload(BaseModel):
    action_taken: str | None = None
    felt_right: str | None = None  # yes | no | unsure
    note: str | None = None


class SunshinePayload(BaseModel):
    """Either a 0–5 scale OR a raw lux value. Scale is mapped server-side."""

    scale: int | None = Field(default=None, ge=0, le=5)
    lux: float | None = Field(default=None, ge=0)


class CurrentStatePayload(BaseModel):
    """Physical state of blinds + windows at submission time.

    `blinds`: group → 0..100 percent down. `windows`: zone → bool open/closed.
    Any subset is fine; missing actuators are not updated.
    """

    blinds: dict[str, int] | None = None
    windows: dict[str, bool] | None = None


class ReadingsPayload(BaseModel):
    ts: datetime | None = None
    zones: dict[str, ZonePayload]
    feedback: FeedbackPayload | None = None
    sunshine: SunshinePayload | None = None
    current_state: CurrentStatePayload | None = None


@router.post("/readings", status_code=201)
def submit_readings(payload: ReadingsPayload, session: Session = Depends(get_session)):
    ts = payload.ts or datetime.now(tz=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    rows = [
        Reading(
            ts=ts,
            zone=zone,
            temp_c=z.temp_c,
            humidity_pct=z.humidity_pct,
            lux_indoor=z.lux_indoor,
            source="manual",
        )
        for zone, z in payload.zones.items()
    ]
    ids = repo.insert_reading_batch(session, rows)
    fb_id: int | None = None
    if payload.feedback is not None:
        fb_id = repo.insert_feedback(
            session,
            Feedback(
                ts=ts,
                action_taken=payload.feedback.action_taken,
                felt_right=payload.feedback.felt_right,
                note=payload.feedback.note,
            ),
        )
    state_ids: list[int] = []
    if payload.current_state is not None:
        cs = payload.current_state
        rows: list[ActuatorState] = []
        for group, pct in (cs.blinds or {}).items():
            if not 0 <= pct <= 100:
                raise HTTPException(status_code=422, detail=f"blind {group} pct out of 0..100")
            rows.append(
                ActuatorState(ts=ts, actuator=f"blind:{group}", value=str(pct), source="manual")
            )
        for zone, is_open in (cs.windows or {}).items():
            rows.append(
                ActuatorState(
                    ts=ts,
                    actuator=f"window:{zone}",
                    value="open" if is_open else "closed",
                    source="manual",
                )
            )
        if rows:
            state_ids = repo.insert_actuator_states(session, rows)
    sun_id: int | None = None
    if payload.sunshine is not None:
        s = payload.sunshine
        if s.lux is not None:
            lux = s.lux
            scale = s.scale
        elif s.scale is not None:
            lux = SUNSHINE_SCALE_LUX[s.scale]
            scale = s.scale
        else:
            raise HTTPException(status_code=422, detail="sunshine requires either scale or lux")
        sun_id = repo.insert_sunshine(
            session, Sunshine(ts=ts, lux=lux, scale=scale, source="manual")
        )
    session.commit()
    return {
        "ids": ids,
        "ts": ts.isoformat(),
        "feedback_id": fb_id,
        "sunshine_id": sun_id,
        "state_ids": state_ids,
    }


@router.get("/sunshine/scale")
def sunshine_scale():
    """Expose the manual sunshine scale → lux mapping so the frontend can render it."""
    return {
        "items": [
            {"step": k, "label": SUNSHINE_SCALE_LABELS[k], "lux": SUNSHINE_SCALE_LUX[k]}
            for k in sorted(SUNSHINE_SCALE_LUX.keys())
        ]
    }


@router.get("/sunshine/latest")
def sunshine_latest(session: Session = Depends(get_session)):
    row = repo.latest_sunshine(session)
    if row is None:
        return {"sunshine": None}
    return {
        "sunshine": {
            "ts": row.ts.isoformat(),
            "lux": row.lux,
            "scale": row.scale,
        }
    }


@router.get("/readings/latest")
def latest(session: Session = Depends(get_session)):
    out = {}
    for zone, r in repo.latest_per_zone(session).items():
        out[zone] = {
            "ts": r.ts.isoformat(),
            "temp_c": r.temp_c,
            "humidity_pct": r.humidity_pct,
            "lux_indoor": r.lux_indoor,
        }
    return {"zones": out}
