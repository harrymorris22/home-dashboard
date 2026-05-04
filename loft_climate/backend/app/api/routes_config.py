from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.config.loader import load_config, save_config
from app.config.schema import ConfigV1

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_config():
    return load_config().model_dump(mode="json")


@router.put("/config")
def put_config(payload: dict):
    try:
        cfg = ConfigV1.model_validate(payload)
    except ValidationError as e:
        # Strip ctx/url/etc. to keep the detail JSON-serialisable.
        detail = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in e.errors()
        ]
        raise HTTPException(status_code=422, detail=detail)
    save_config(cfg)
    return cfg.model_dump(mode="json")
