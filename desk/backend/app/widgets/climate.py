"""Climate widget — proxies the loft_climate Add-on's /api/state.

Cross-Add-on hop uses HA Supervisor's per-Add-on DNS (`local_<slug>`). No
auth: the Supervisor only exposes Add-ons to each other on the internal
network. Frontend never makes the cross-origin call directly.

On upstream failure (5xx, timeout, connection refused, DNS error): serve the
most recent successful body with `stale: true`. Frontend renders a degraded
badge. Climate Add-on stopped, restarting, or temporarily unreachable should
NOT make the desk dashboard's climate tile show "—" — show what we know.

# Request flow
#
# GET /api/widgets/climate
#   ├─> cache fresh (<60s old)? → return cached
#   ├─> upstream call (httpx GET local_loft_climate:8000/api/state, 5s timeout)
#   │    ├─> 200 → project to summary + update cache + return
#   │    └─> any failure → fall back to last cached → return with stale=true
#   └─> never cached AND upstream down → return 503 with clear message
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TTL = timedelta(seconds=60)

# Single in-process cache. One widget, one consumer — no need for Redis.
_cache: dict[str, Any] = {
    "fetched_at": None,  # datetime | None
    "payload": None,     # dict | None
    "stale": False,
}
_lock = asyncio.Lock()


def _project(state: dict[str, Any]) -> dict[str, Any]:
    """Reduce the climate StateBundle to the summary tile shape."""
    rec = state.get("recommendations", {}) or {}
    global_ = rec.get("global", {}) or {}
    sensors = state.get("sensors", {}) or {}
    bedroom = sensors.get("bedroom", {}) or {}
    prompts = rec.get("prompts", []) or []
    return {
        "scenario": global_.get("scenario") or "unknown",
        "urgency": global_.get("urgency") or "green",
        "bedroom_temp_c": bedroom.get("temp_c"),
        "prompt": prompts[0] if prompts else None,
        "ts": state.get("ts"),
    }


@router.get("/api/widgets/climate")
async def climate() -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.loft_internal_url.rstrip('/')}/api/state"
    now = datetime.now(tz=timezone.utc)

    async with _lock:
        fetched_at = _cache["fetched_at"]
        if (
            fetched_at is not None
            and _cache["payload"] is not None
            and (now - fetched_at) < _CACHE_TTL
        ):
            # Fresh cache hit — return as-is.
            return {**_cache["payload"], "stale": False, "last_success_at": fetched_at.isoformat()}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
            resp.raise_for_status()
            projected = _project(resp.json())
            _cache["payload"] = projected
            _cache["fetched_at"] = now
            _cache["stale"] = False
            return {**projected, "stale": False, "last_success_at": now.isoformat()}
        except (httpx.HTTPError, ValueError) as e:
            log.warning("[climate widget] upstream failure (%s): %s", type(e).__name__, e)
            if _cache["payload"] is not None:
                # Stale-cache fallback (eng-review 1B).
                return {
                    **_cache["payload"],
                    "stale": True,
                    "last_success_at": _cache["fetched_at"].isoformat()
                    if _cache["fetched_at"]
                    else None,
                }
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "climate_upstream_unreachable",
                    "message": f"Could not reach {url} and have no cached data yet.",
                },
            )
