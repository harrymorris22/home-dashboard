"""Oura widget — OAuth2 step-count proxy.

Authenticates to Oura via authorization-code flow. User completes consent
once; backend persists a single-use rotating refresh_token to disk and
mints fresh access_tokens on demand (and every 12h via a proactive task).

# Security invariants
#  - Tokens never reach the browser (backend-only)
#  - client_secret never logged, never in response bodies
#  - Authorization headers never logged
#  - resp.text from Oura never logged (may echo headers)
#  - _project() drops every upstream field except step counts + timestamp
#  - HMAC-signed state token (no server-side state storage; restart-proof)
#  - Atomic token write with fsync (durable across SD-card power loss)

# Critical correctness
#  - _get_valid_access_token() re-reads tokens AFTER acquiring _token_lock —
#    prevents thundering-herd refresh of an already-rotated (invalidated)
#    refresh_token.
#  - 401 on data fetch triggers one refresh-and-retry. Distinguishes
#    "access_token just expired" from "user revoked app".

# Known limitation
#  - If the Pi loses power between Oura returning new tokens and os.replace()
#    completing, the old (now-invalidated) refresh_token persists. Next
#    refresh returns 401, tokens are deleted, user reconnects. The log line
#    "refresh rotation persisted" follows the replace so post-mortem is easy.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TTL = timedelta(minutes=5)
_ACCESS_TOKEN_REFRESH_MARGIN = timedelta(minutes=5)
_STATE_MAX_AGE_S = 600  # 10 minutes
_PROACTIVE_REFRESH_INTERVAL_S = 12 * 3600

LONDON = ZoneInfo("Europe/London")
_OURA_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
_OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"
_OURA_DAILY_URL = "https://api.ouraring.com/v2/usercollection/daily_activity"

# Cache for the summary endpoint's projected payload (separate from tokens).
_data_cache: dict[str, Any] = {"fetched_at": None, "payload": None}
_data_lock = asyncio.Lock()
# Serializes refresh-token rotation within process.
_token_lock = asyncio.Lock()


# ── Path helpers ───────────────────────────────────────────────────────────


def _tokens_path() -> Path:
    """Tokens file path. Env var wins so HA Supervisor's /data mount works."""
    env_path = os.environ.get("OURA_TOKENS_PATH")
    if env_path:
        return Path(env_path)
    return get_settings().oura_tokens_path


def _redirect_uri() -> str:
    base = get_settings().dashboard_base_url.rstrip("/")
    return f"{base}/api/widgets/oura/oauth/callback"


# ── Token storage (atomic with fsync) ──────────────────────────────────────


def _read_tokens() -> dict | None:
    path = _tokens_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        log.warning("[oura widget] tokens file unreadable; treating as absent")
        return None


def _write_tokens_atomic(payload: dict) -> None:
    """Write tokens with durability: tmpfile + flush + fsync + os.replace."""
    path = _tokens_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as fd:
        json.dump(payload, fd, indent=2)
        fd.flush()
        os.fsync(fd.fileno())
    os.replace(tmp, path)


def _delete_tokens() -> None:
    path = _tokens_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ── HMAC-signed state (no server-side storage; restart-proof) ──────────────


def _state_key() -> bytes:
    """Derive HMAC key from client_secret. Key naturally rotates with creds."""
    secret = (get_settings().oura_client_secret or "").encode("utf-8")
    return hmac.new(b"oauth_state", secret, hashlib.sha256).digest()


def _build_state() -> str:
    nonce = secrets.token_bytes(16)
    ts = int(time.time()).to_bytes(8, "big")
    payload = nonce + ts
    sig = hmac.new(_state_key(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + sig).decode("ascii")


def _verify_state(state: str | None, max_age_s: int = _STATE_MAX_AGE_S) -> bool:
    if not state:
        return False
    try:
        raw = base64.urlsafe_b64decode(state.encode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return False
    # 16 byte nonce + 8 byte timestamp + 32 byte HMAC-SHA256
    if len(raw) != 56:
        return False
    payload, sig = raw[:24], raw[24:]
    expected = hmac.new(_state_key(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False
    ts = int.from_bytes(payload[16:24], "big")
    return (time.time() - ts) <= max_age_s


# ── Date helpers (DST-safe, independently testable) ────────────────────────


def _london_today_yesterday(now_utc: datetime) -> tuple[str, str]:
    """Return (today_iso, yesterday_iso) in Europe/London local time."""
    today_local = now_utc.astimezone(LONDON).date()
    yesterday_local = today_local - timedelta(days=1)
    return today_local.isoformat(), yesterday_local.isoformat()


# ── Projection ─────────────────────────────────────────────────────────────


def _project(api_response: dict, today_iso: str, yesterday_iso: str) -> dict:
    """Pick today + yesterday entries from Oura's daily_activity response.

    Filters by exact day match (Oura may return adjacent days). Value 0
    propagates as 0, distinct from None.
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


# ── Token-refresh helper (critical correctness path) ───────────────────────


def _credentials_configured() -> bool:
    s = get_settings()
    return bool((s.oura_client_id or "").strip()) and bool((s.oura_client_secret or "").strip())


async def _get_valid_access_token() -> str:
    """Return a valid access_token, refreshing if needed.

    Re-reads tokens AFTER lock acquisition so a thundering-herd of waiters
    doesn't all try to refresh with the same (now-invalidated by the winner's
    rotation) refresh_token.
    """
    if not _credentials_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "oura_oauth_not_configured",
                "instruction": (
                    "Set Oura credentials in Add-on options. Create an "
                    "application at cloud.ouraring.com/oauth/applications, "
                    "paste Client ID and Client Secret, then restart."
                ),
            },
        )

    async with _token_lock:
        tokens = _read_tokens()
        if tokens is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "oura_not_connected",
                    "instruction": "Click Connect Oura on the dashboard.",
                },
            )
        # If credentials were rotated, stored tokens are now meaningless.
        stored_client_id = tokens.get("client_id")
        current_client_id = (get_settings().oura_client_id or "").strip()
        if stored_client_id and stored_client_id != current_client_id:
            log.info("[oura widget] client_id rotation detected; deleting old tokens")
            _delete_tokens()
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "oura_not_connected",
                    "instruction": "Click Connect Oura on the dashboard.",
                },
            )

        try:
            expires_at = datetime.fromisoformat(tokens["expires_at"])
        except (KeyError, ValueError):
            log.warning("[oura widget] tokens file malformed; deleting")
            _delete_tokens()
            raise HTTPException(
                status_code=503,
                detail={"error": "oura_not_connected", "instruction": "Click Connect Oura."},
            )

        now = datetime.now(tz=timezone.utc)
        if (expires_at - now) > _ACCESS_TOKEN_REFRESH_MARGIN:
            # Re-check inside lock — a previous waiter may have just refreshed.
            return tokens["access_token"]

        # Single-use refresh — rotate atomically
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    _OURA_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": tokens["refresh_token"],
                        "client_id": current_client_id,
                        "client_secret": (get_settings().oura_client_secret or "").strip(),
                    },
                )
        except httpx.HTTPError as e:
            log.warning("[oura widget] refresh network error (%s)", type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail={"error": "oura_fetch_failed", "message": "Could not reach Oura API."},
            )

        if resp.status_code == 401:
            log.info("[oura widget] refresh rejected by Oura — deleting tokens")
            _delete_tokens()
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "oura_token_invalid",
                    "instruction": (
                        "Token expired or revoked. Click Reconnect Oura on the dashboard."
                    ),
                },
            )

        if resp.status_code >= 400:
            log.warning("[oura widget] refresh unexpected status=%d", resp.status_code)
            raise HTTPException(
                status_code=502,
                detail={"error": "oura_fetch_failed", "message": "Oura refused refresh."},
            )

        try:
            body = resp.json()
        except (ValueError, json.JSONDecodeError):
            log.warning("[oura widget] refresh response not JSON")
            raise HTTPException(
                status_code=502,
                detail={"error": "oura_fetch_failed", "message": "Bad Oura response."},
            )

        try:
            new_tokens = {
                "access_token": body["access_token"],
                "refresh_token": body["refresh_token"],
                "expires_at": (now + timedelta(seconds=int(body["expires_in"]))).isoformat(),
                "obtained_at": now.isoformat(),
                "client_id": current_client_id,
            }
        except (KeyError, TypeError, ValueError):
            log.warning("[oura widget] refresh response missing fields")
            raise HTTPException(
                status_code=502,
                detail={"error": "oura_fetch_failed", "message": "Malformed Oura response."},
            )

        _write_tokens_atomic(new_tokens)
        log.info("[oura widget] refresh rotation persisted")
        return new_tokens["access_token"]


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/api/widgets/oura/summary")
async def oura_summary() -> dict[str, Any]:
    if not _credentials_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "oura_oauth_not_configured",
                "instruction": (
                    "Set Oura credentials in Add-on options."
                ),
            },
        )
    if _read_tokens() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "oura_not_connected",
                "instruction": "Click Connect Oura on the dashboard.",
            },
        )

    now = datetime.now(tz=timezone.utc)
    today_iso, yesterday_iso = _london_today_yesterday(now)

    async with _data_lock:
        fetched_at = _data_cache["fetched_at"]
        if (
            fetched_at is not None
            and _data_cache["payload"] is not None
            and (now - fetched_at) < _CACHE_TTL
        ):
            return {
                **_data_cache["payload"],
                "stale": False,
                "last_success_at": fetched_at.isoformat(),
            }

        try:
            access_token = await _get_valid_access_token()
            payload = await _fetch_with_token_retry(access_token, today_iso, yesterday_iso)
        except HTTPException:
            # 503 oura_not_connected / oura_token_invalid / 502 oura_fetch_failed —
            # if we have cached data, serve stale; otherwise re-raise.
            if _data_cache["payload"] is not None:
                return {
                    **_data_cache["payload"],
                    "stale": True,
                    "last_success_at": _data_cache["fetched_at"].isoformat()
                    if _data_cache["fetched_at"] else None,
                }
            raise

        projected = _project(payload, today_iso, yesterday_iso)
        _data_cache["payload"] = projected
        _data_cache["fetched_at"] = now
        return {**projected, "stale": False, "last_success_at": now.isoformat()}


async def _fetch_with_token_retry(
    access_token: str, today_iso: str, yesterday_iso: str
) -> dict:
    """Fetch daily_activity; on 401, refresh once and retry."""
    url = f"{_OURA_DAILY_URL}?start_date={yesterday_iso}&end_date={today_iso}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {access_token}"}
            )
    except httpx.HTTPError as e:
        log.warning("[oura widget] data fetch network error (%s)", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail={"error": "oura_fetch_failed", "message": "Could not reach Oura API."},
        )

    if resp.status_code == 401:
        # Access token revoked or expired between refresh and fetch — try once more.
        log.info("[oura widget] 401 on data fetch; forcing refresh-and-retry")
        # Invalidate current access by clearing expiry; next _get_valid_access_token
        # will refresh. We can also just call refresh directly.
        tokens = _read_tokens()
        if tokens is not None:
            tokens["expires_at"] = datetime.now(tz=timezone.utc).isoformat()
            _write_tokens_atomic(tokens)
        retry_token = await _get_valid_access_token()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp2 = await client.get(
                    url, headers={"Authorization": f"Bearer {retry_token}"}
                )
        except httpx.HTTPError as e:
            log.warning("[oura widget] retry network error (%s)", type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail={"error": "oura_fetch_failed", "message": "Could not reach Oura."},
            )
        if resp2.status_code == 401:
            log.info("[oura widget] data fetch 401 after retry — deleting tokens")
            _delete_tokens()
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "oura_token_invalid",
                    "instruction": "Token revoked. Click Reconnect Oura.",
                },
            )
        resp = resp2

    if resp.status_code >= 400:
        log.warning("[oura widget] data fetch status=%d", resp.status_code)
        raise HTTPException(
            status_code=502,
            detail={"error": "oura_fetch_failed", "message": "Oura returned error."},
        )
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError):
        log.warning("[oura widget] data fetch response not JSON")
        raise HTTPException(
            status_code=502,
            detail={"error": "oura_fetch_failed", "message": "Bad Oura response."},
        )


@router.get("/api/widgets/oura/oauth/start")
async def oauth_start() -> RedirectResponse:
    s = get_settings()
    client_id = (s.oura_client_id or "").strip()
    if not client_id or not (s.oura_client_secret or "").strip():
        raise HTTPException(
            status_code=503,
            detail={"error": "oura_oauth_not_configured", "instruction": "Set credentials."},
        )
    state = _build_state()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "scope": "daily",
        "state": state,
    }
    url = f"{_OURA_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


def _dashboard_redirect(query: str = "") -> RedirectResponse:
    base = get_settings().dashboard_base_url.rstrip("/")
    target = f"{base}/{('?' + query) if query else ''}"
    resp = RedirectResponse(url=target, status_code=303)
    resp.headers["Content-Security-Policy"] = "default-src 'none'"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


@router.get("/api/widgets/oura/oauth/callback")
async def oauth_callback(request: Request) -> RedirectResponse:
    params = request.query_params
    state = params.get("state")
    code = params.get("code")
    if not _verify_state(state):
        log.info("[oura widget] callback rejected: invalid/expired state")
        return _dashboard_redirect("oauth_error=oauth_state_invalid")
    if not code:
        return _dashboard_redirect("oauth_error=oauth_code_missing")

    s = get_settings()
    client_id = (s.oura_client_id or "").strip()
    client_secret = (s.oura_client_secret or "").strip()
    if not client_id or not client_secret:
        return _dashboard_redirect("oauth_error=oura_oauth_not_configured")

    now = datetime.now(tz=timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _OURA_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
    except httpx.HTTPError as e:
        log.warning("[oura widget] callback token-exchange network error (%s)", type(e).__name__)
        return _dashboard_redirect("oauth_error=token_exchange_failed")

    if resp.status_code >= 400:
        log.warning("[oura widget] callback token-exchange status=%d", resp.status_code)
        return _dashboard_redirect("oauth_error=token_exchange_failed")

    try:
        body = resp.json()
        tokens = {
            "access_token": body["access_token"],
            "refresh_token": body["refresh_token"],
            "expires_at": (now + timedelta(seconds=int(body["expires_in"]))).isoformat(),
            "obtained_at": now.isoformat(),
            "client_id": client_id,
        }
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        log.warning("[oura widget] callback response malformed")
        return _dashboard_redirect("oauth_error=token_exchange_failed")

    _write_tokens_atomic(tokens)
    log.info("[oura widget] initial OAuth exchange persisted")
    return _dashboard_redirect("connected=1")


@router.post("/api/widgets/oura/oauth/disconnect")
async def oauth_disconnect() -> dict[str, bool]:
    _delete_tokens()
    return {"disconnected": True}


# TEMPORARY DIAGNOSTIC — remove after debugging the "today is null" issue.
# Returns the last 8 days' (day, steps, timezone) from Oura's daily_activity
# so we can see what date keys Oura actually returns vs what we query for.
@router.get("/api/widgets/oura/_debug")
async def oura_debug() -> dict[str, Any]:
    token = await _get_valid_access_token()
    now = datetime.now(tz=timezone.utc)
    today_iso, yesterday_iso = _london_today_yesterday(now)
    london_today = datetime.now(tz=LONDON).date()
    window_start = (london_today - timedelta(days=7)).isoformat()
    window_end = (london_today + timedelta(days=1)).isoformat()
    url = f"{_OURA_DAILY_URL}?start_date={window_start}&end_date={window_end}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    try:
        body = resp.json() if resp.status_code == 200 else {}
    except (ValueError, json.JSONDecodeError):
        body = {}
    days = [
        {
            "day": r.get("day"),
            "steps": r.get("steps"),
            "timezone": r.get("timezone"),
        }
        for r in (body.get("data") or [])
        if isinstance(r, dict)
    ]
    return {
        "status": resp.status_code,
        "today_requested": today_iso,
        "yesterday_requested": yesterday_iso,
        "window_requested": [window_start, window_end],
        "now_utc": now.isoformat(),
        "now_london": datetime.now(tz=LONDON).isoformat(),
        "days_returned": days,
    }


# ── Proactive refresh task ─────────────────────────────────────────────────


async def proactive_refresh_loop() -> None:
    """Background task: refresh once every 12h to keep the chain warm."""
    while True:
        await asyncio.sleep(_PROACTIVE_REFRESH_INTERVAL_S)
        try:
            await _get_valid_access_token()
            log.info("[oura widget] proactive refresh tick ok")
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {}
            log.warning(
                "[oura widget] proactive refresh failed: %s", detail.get("error", "unknown")
            )
        except Exception:  # noqa: BLE001
            log.exception("[oura widget] proactive refresh crashed")
