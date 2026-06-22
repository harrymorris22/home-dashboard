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

# Blind-action threshold: ignore deltas below this many percentage points so
# the tile doesn't nag the user about a 10% nudge they'd shrug at anyway.
BLIND_ACTION_THRESHOLD = 15

# Module-level flag — log the "older upstream, no current_state" message once
# per process so half-deployed systems are diagnosable without log spam.
_warned_no_current_state = False


def _warn_if_legacy_upstream(state: dict[str, Any]) -> None:
    global _warned_no_current_state
    if _warned_no_current_state:
        return
    if "current_state" not in state:
        log.info(
            "[climate widget] upstream /api/state missing current_state — "
            "action lines disabled; upgrade loft_climate to enable"
        )
        _warned_no_current_state = True


def _window_actions(rec_by_zone: dict, current_windows: dict) -> list[dict]:
    """Return a list of window-open/close actions where current ≠ recommended."""
    actions: list[dict] = []
    for zone, r in rec_by_zone.items():
        if not isinstance(r, dict):
            continue
        recommended = r.get("window_open")
        if recommended is None:
            continue
        current = current_windows.get(zone)
        if current is None or current == recommended:
            continue
        actions.append({"zone": zone, "action": "open" if recommended else "close"})
    return actions


def _blind_actions(rec_by_group: dict, current_blinds: dict) -> list[dict]:
    """Return blind-raise/lower actions where |target - current| ≥ threshold."""
    actions: list[dict] = []
    for group, r in rec_by_group.items():
        if not isinstance(r, dict):
            continue
        if r.get("scenario") == "neutral":
            continue
        target = r.get("blind_pct")
        if target is None:
            continue
        current = current_blinds.get(group)
        if current is None:
            continue
        delta = target - current
        if abs(delta) < BLIND_ACTION_THRESHOLD:
            continue
        actions.append({
            "group": group,
            "current_pct": current,
            "target_pct": target,
            "direction": "lower" if delta < 0 else "raise",
        })
    return actions


# CONTRACT: This function reads the following upstream fields. If loft_climate's
# /api/state serializer changes, update this list AND test_climate_proxy.py.
#   state["ts"], state["sensors"]["mezzanine"]["temp_c"],
#   state["current_state"]["windows"]: dict[str, bool],
#   state["current_state"]["blinds"]: dict[str, int],
#   state["recommendations"]["global"]["scenario"|"urgency"],
#   state["recommendations"]["by_zone"][zone]["window_open"],
#   state["recommendations"]["by_blind_group"][group]["blind_pct"|"scenario"],
#   state["recommendations"]["prompts"]
# See loft_climate/backend/app/api/_serialise.py for the upstream contract.
def _project(state: dict[str, Any]) -> dict[str, Any]:
    """Reduce the climate StateBundle to the summary tile shape."""
    _warn_if_legacy_upstream(state)
    rec = state.get("recommendations") or {}
    global_ = rec.get("global") or {}
    sensors = state.get("sensors") or {}
    current = state.get("current_state") or {}
    mezz = sensors.get("mezzanine") or {}
    prompts = rec.get("prompts") or []
    return {
        "scenario": global_.get("scenario") or "unknown",
        "urgency": global_.get("urgency") or "green",
        "office_temp_c": mezz.get("temp_c"),
        "window_actions": _window_actions(
            rec.get("by_zone") or {}, current.get("windows") or {}
        ),
        "blind_actions": _blind_actions(
            rec.get("by_blind_group") or {}, current.get("blinds") or {}
        ),
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
