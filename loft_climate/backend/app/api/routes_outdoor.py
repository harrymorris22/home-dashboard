"""Outdoor sensor bias curve — inspect the fit and force a recalibration.

Frontend uses ``GET /api/outdoor/bias`` to render the calibration card
(hourly bar chart + fitted_at timestamp) and ``POST /api/outdoor/bias``
for the "Recalibrate now" button.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.loader import load_config
from app.db import repo
from app.db.session import get_session
from app.outdoor.calibrator import run_calibration
from app.settings import get_settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/outdoor", tags=["outdoor"])


def _serialise(row) -> dict:
    return {
        "fitted_at": row.fitted_at.isoformat(),
        "days_window": row.days_window,
        "bias_by_hour": json.loads(row.bias_by_hour_json),
        "sample_counts": json.loads(row.sample_counts_json),
    }


@router.get("/bias")
def get_bias(session: Session = Depends(get_session)):
    """Latest fitted bias curve + the correction settings currently in use."""
    cfg = load_config()
    row = repo.latest_outdoor_calibration(session)
    return {
        "calibration": _serialise(row) if row is not None else None,
        "settings": _settings_payload(cfg),
    }


def _settings_payload(cfg) -> dict:
    return {
        "correction": cfg.outdoor.correction,
        "microclimate_baseline_c": cfg.outdoor.microclimate_baseline_c,
        "clearness_floor": cfg.outdoor.clearness_floor,
        "fit_window_days": cfg.outdoor.fit_window_days,
        "fit_interval_days": cfg.outdoor.fit_interval_days,
    }


@router.post("/bias")
async def recalibrate(
    request: Request,
    session: Session = Depends(get_session),
):
    """Force an immediate refit. Returns the same envelope as GET so the
    frontend can drop this into its SWR cache without losing ``settings``.
    400 if the outdoor sensor entity isn't configured, 503 if the HA
    client is not yet available (add-on still starting)."""
    cfg = load_config()
    app_settings = get_settings()
    outdoor_entity = app_settings.ha_outdoor_entities.get("temp")
    if not outdoor_entity:
        raise HTTPException(
            status_code=400,
            detail="ha_outdoor_entities.temp not configured — no sensor to calibrate",
        )
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None:
        raise HTTPException(
            status_code=503,
            detail="HA client not available (add-on still starting?)",
        )
    row = await run_calibration(session, ha_client, cfg, outdoor_entity)
    resp: dict = {
        "calibration": _serialise(row) if row is not None else None,
        "settings": _settings_payload(cfg),
    }
    if row is None:
        resp["note"] = (
            "No overlapping SwitchBot + Met.no history yet. "
            "Try again after a day or so."
        )
    return resp
