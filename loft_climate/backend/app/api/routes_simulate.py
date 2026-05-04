from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api._serialise import serialise_recommendation
from app.config.loader import load_config
from app.engine.engine import decide
from app.simulation.scenarios import SCENARIOS

router = APIRouter(prefix="/api/simulate", tags=["simulate"])


class SimulateRequest(BaseModel):
    scenario_name: str | None = None


@router.get("/scenarios")
def list_scenarios():
    return {"scenarios": list(SCENARIOS.keys())}


@router.post("")
def run_simulation(req: SimulateRequest):
    if not req.scenario_name:
        raise HTTPException(status_code=422, detail="scenario_name required")
    builder = SCENARIOS.get(req.scenario_name)
    if builder is None:
        raise HTTPException(status_code=404, detail=f"unknown scenario {req.scenario_name!r}")
    cfg = load_config()
    snap = builder(cfg)
    rec = decide(snap)
    return {
        "scenario_name": req.scenario_name,
        "recommendations": serialise_recommendation(rec),
    }
