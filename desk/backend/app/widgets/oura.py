"""Oura widget — daily step count proxy.

Pulls 2-day daily_activity from api.ouraring.com with a Bearer PAT.
In-process 5-min TTL cache; on upstream failure with cached data, serves
stale. Token is never logged; token never leaves the backend (frontend
hits /api/widgets/oura/summary, never api.ouraring.com).

# Security invariants
#  - NEVER log repr(headers) or any header value
#  - NEVER log resp.text on error (Oura may echo headers in error bodies)
#  - _project() drops every upstream field except step counts + timestamp —
#    token cannot survive in the cached payload
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException

from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TTL = timedelta(minutes=5)
LONDON = ZoneInfo("Europe/London")
_OURA_BASE = "https://api.ouraring.com/v2/usercollection/daily_activity"

_cache: dict[str, Any] = {"fetched_at": None, "payload": None, "stale": False}
_lock = asyncio.Lock()


def _london_today_yesterday(now_utc: datetime) -> tuple[str, str]:
    """Return (today_iso, yesterday_iso) in Europe/London local time. DST-safe."""
    today_local = now_utc.astimezone(LONDON).date()
    yesterday_local = today_local - timedelta(days=1)
    return today_local.isoformat(), yesterday_local.isoformat()


def _project(api_response: dict, today_iso: str, yesterday_iso: str) -> dict:
    """Pick today + yesterday entries from Oura's daily_activity response.

    Oura may return adjacent days outside the requested window — filter by
    exact day match, not array index. Either count may be None if Oura
    hasn't synced that day yet (common right after midnight London time).
    Value 0 must propagate as 0, distinct from None.
    """
    days = {
        row.get("day"): row.get("steps")
        for row in (api_response.get("data") or [])
        if isinstance(row, dict)
    }
    return {
        "step_count": days.get(today_iso),
        "step_count_yesterday": days.get(yesterday_iso),
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }


def _stale_or_502() -> dict[str, Any]:
    if _cache["payload"] is not None:
        return {
            **_cache["payload"],
            "stale": True,
            "last_success_at": _cache["fetched_at"].isoformat()
            if _cache["fetched_at"]
            else None,
        }
    raise HTTPException(
        status_code=502,
        detail={
            "error": "oura_fetch_failed",
            "message": "Could not reach Oura API and have no cached data yet.",
        },
    )


@router.get("/api/widgets/oura/summary")
async def oura_summary() -> dict[str, Any]:
    settings = get_settings()
    token = (settings.oura_pat_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "oura_pat_token_not_configured",
                "instruction": (
                    "Get a Personal Access Token at cloud.ouraring.com → "
                    "Personal Access Tokens → Create New, then set "
                    "oura_pat_token in the Desk Dashboard Add-on options."
                ),
            },
        )

    now = datetime.now(tz=timezone.utc)
    today_iso, yesterday_iso = _london_today_yesterday(now)

    async with _lock:
        fetched_at = _cache["fetched_at"]
        if (
            fetched_at is not None
            and _cache["payload"] is not None
            and (now - fetched_at) < _CACHE_TTL
        ):
            return {
                **_cache["payload"],
                "stale": False,
                "last_success_at": fetched_at.isoformat(),
            }

        url = f"{_OURA_BASE}?start_date={yesterday_iso}&end_date={today_iso}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as e:
            log.warning("[oura widget] network error (%s)", type(e).__name__)
            return _stale_or_502()

        if resp.status_code == 401:
            log.info("[oura widget] 401 from Oura — token rejected")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "oura_token_invalid",
                    "instruction": (
                        "PAT rejected by Oura. Token may have been revoked or "
                        "mistyped. Re-create one at cloud.ouraring.com → "
                        "Personal Access Tokens."
                    ),
                },
            )
        if resp.status_code >= 500 or resp.status_code in (408, 429):
            log.warning("[oura widget] upstream %d", resp.status_code)
            return _stale_or_502()

        try:
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning(
                "[oura widget] unexpected response status=%d type=%s",
                resp.status_code,
                type(e).__name__,
            )
            return _stale_or_502()

        projected = _project(payload, today_iso, yesterday_iso)
        _cache["payload"] = projected
        _cache["fetched_at"] = now
        _cache["stale"] = False
        return {**projected, "stale": False, "last_success_at": now.isoformat()}
