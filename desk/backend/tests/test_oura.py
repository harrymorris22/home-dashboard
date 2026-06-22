"""Oura widget tests — OAuth flow, token rotation, data fetch, helpers.

Covers the CSRF matrix, concurrent refresh (exactly-one-HTTP), 401 refresh-
and-retry on data fetch, atomic write protocol, settings validation, and
all pure helpers (_project, _london_today_yesterday, _build_state/_verify_state).
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import get_settings
from app.widgets import oura as oura_mod
from app.widgets.oura import (
    _build_state,
    _london_today_yesterday,
    _project,
    _verify_state,
)


CLIENT_ID = "test-client-id-abc"
CLIENT_SECRET = "test-client-secret-xyz"


def _mock_response(status: int = 200, json_data=None) -> httpx.Response:
    if json_data is None:
        json_data = {}
    return httpx.Response(
        status, json=json_data, request=httpx.Request("GET", "http://x")
    )


def _make_oura_payload(days: list[dict]) -> dict:
    return {"data": days, "next_token": None}


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    """Reset all module-level state + settings + tokens path between tests."""
    tokens_file = tmp_path / "oura_tokens.json"
    monkeypatch.setenv("OURA_TOKENS_PATH", str(tokens_file))

    s = get_settings()
    s.oura_client_id = CLIENT_ID
    s.oura_client_secret = CLIENT_SECRET
    s.dashboard_base_url = "https://desk.test"

    oura_mod._data_cache["payload"] = None
    oura_mod._data_cache["fetched_at"] = None

    yield tokens_file

    s.oura_client_id = ""
    s.oura_client_secret = ""
    s.dashboard_base_url = "https://desk.harrymorris.me"
    oura_mod._data_cache["payload"] = None
    oura_mod._data_cache["fetched_at"] = None


def _write_test_tokens(tokens_file, expires_in_minutes: int = 60, refresh_token: str = "r-old"):
    now = datetime.now(tz=timezone.utc)
    payload = {
        "access_token": "a-current",
        "refresh_token": refresh_token,
        "expires_at": (now + timedelta(minutes=expires_in_minutes)).isoformat(),
        "obtained_at": now.isoformat(),
        "client_id": CLIENT_ID,
    }
    tokens_file.parent.mkdir(parents=True, exist_ok=True)
    tokens_file.write_text(json.dumps(payload))
    return payload


# ── _verify_state / _build_state ────────────────────────────────────────────


def test_build_and_verify_state_roundtrip():
    state = _build_state()
    assert _verify_state(state) is True


def test_verify_state_none_or_empty():
    assert _verify_state(None) is False
    assert _verify_state("") is False


def test_verify_state_bad_base64():
    assert _verify_state("not!base64$$") is False


def test_verify_state_wrong_length():
    bad = base64.urlsafe_b64encode(b"too short").decode("ascii")
    assert _verify_state(bad) is False


def test_verify_state_tampered_signature():
    state = _build_state()
    raw = bytearray(base64.urlsafe_b64decode(state.encode("ascii")))
    raw[-1] ^= 0x01  # flip a bit in the HMAC
    tampered = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    assert _verify_state(tampered) is False


def test_verify_state_expired():
    # Build a state with a timestamp 1 hour ago
    nonce = b"\x00" * 16
    ts = (int(time.time()) - 3600).to_bytes(8, "big")
    payload = nonce + ts
    key = hmac.new(
        b"oauth_state",
        CLIENT_SECRET.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig = hmac.new(key, payload, hashlib.sha256).digest()
    state = base64.urlsafe_b64encode(payload + sig).decode("ascii")
    assert _verify_state(state, max_age_s=600) is False


def test_verify_state_rejects_after_client_secret_rotation():
    state = _build_state()
    get_settings().oura_client_secret = "different-secret"
    assert _verify_state(state) is False


# ── _project ───────────────────────────────────────────────────────────────


def test_project_both_days_present():
    out = _project(
        _make_oura_payload([
            {"day": "2026-06-21", "steps": 11204},
            {"day": "2026-06-22", "steps": 8432},
        ]),
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] == 8432
    assert out["step_count_yesterday"] == 11204


def test_project_only_yesterday_present():
    out = _project(
        _make_oura_payload([{"day": "2026-06-21", "steps": 11204}]),
        "2026-06-22", "2026-06-21",
    )
    assert out["step_count"] is None
    assert out["step_count_yesterday"] == 11204


def test_project_neither_day_present():
    out = _project(
        _make_oura_payload([{"day": "2026-06-15", "steps": 7000}]),
        "2026-06-22", "2026-06-21",
    )
    assert out["step_count"] is None
    assert out["step_count_yesterday"] is None


def test_project_empty_data():
    out = _project(_make_oura_payload([]), "2026-06-22", "2026-06-21")
    assert out["step_count"] is None
    assert out["step_count_yesterday"] is None


def test_project_filters_extra_days():
    out = _project(
        _make_oura_payload([
            {"day": "2026-06-19", "steps": 1000},
            {"day": "2026-06-20", "steps": 2000},
            {"day": "2026-06-21", "steps": 3000},
            {"day": "2026-06-22", "steps": 4000},
            {"day": "2026-06-23", "steps": 5000},
        ]),
        "2026-06-22", "2026-06-21",
    )
    assert out["step_count"] == 4000
    assert out["step_count_yesterday"] == 3000


def test_project_zero_propagates():
    out = _project(
        _make_oura_payload([{"day": "2026-06-22", "steps": 0}]),
        "2026-06-22", "2026-06-21",
    )
    assert out["step_count"] == 0
    assert out["step_count"] is not None


def test_project_non_dict_rows_skipped():
    out = _project(
        {"data": ["not a dict", None, {"day": "2026-06-22", "steps": 5000}]},
        "2026-06-22", "2026-06-21",
    )
    assert out["step_count"] == 5000


def test_project_data_none():
    assert _project({"data": None}, "2026-06-22", "2026-06-21")["step_count"] is None


# ── _london_today_yesterday (DST) ──────────────────────────────────────────


def test_london_midday_utc():
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now)
    assert today == "2026-06-22"
    assert yesterday == "2026-06-21"


def test_london_late_evening_summer():
    now = datetime(2026, 6, 22, 22, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now)
    assert today == "2026-06-22"


def test_london_after_midnight_summer():
    now = datetime(2026, 6, 23, 1, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now)
    assert today == "2026-06-23"
    assert yesterday == "2026-06-22"


def test_london_spring_forward():
    now = datetime(2026, 3, 30, 1, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now)
    assert today == "2026-03-30"


def test_london_autumn_back():
    now = datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now)
    assert today == "2026-10-26"


# ── /api/widgets/oura/summary ──────────────────────────────────────────────


def test_summary_unconfigured_returns_503_oauth_not_configured():
    get_settings().oura_client_id = ""
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_oauth_not_configured"


def test_summary_whitespace_client_secret_treated_as_unconfigured():
    get_settings().oura_client_secret = "   "
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_oauth_not_configured"


def test_summary_configured_but_no_tokens_returns_oura_not_connected(_reset_state):
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_not_connected"


def test_summary_happy_path_uses_cached_access_token(_reset_state):
    _write_test_tokens(_reset_state, expires_in_minutes=60)
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([
        {"day": today_iso, "steps": 8432},
        {"day": yesterday_iso, "steps": 11204},
    ])
    captured_headers = {}

    async def fake_get(url, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return _mock_response(200, payload)

    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=fake_get)
        instance.post = AsyncMock()  # should not be called
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["step_count"] == 8432
    assert body["step_count_yesterday"] == 11204
    assert body["stale"] is False
    assert captured_headers.get("Authorization") == "Bearer a-current"
    # No refresh call happened — access_token had 60min left.
    instance.post.assert_not_called()


def test_summary_requests_end_date_as_tomorrow_london(_reset_state):
    """Regression: Oura's daily_activity end_date excludes today's in-progress
    row. We must request through tomorrow (today + 1 day in Europe/London)
    so today's row is included in the response."""
    _write_test_tokens(_reset_state, expires_in_minutes=60)
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    london_today = datetime.now(tz=oura_mod.LONDON).date()
    expected_end = (london_today + timedelta(days=1)).isoformat()
    payload = _make_oura_payload([
        {"day": today_iso, "steps": 8432},
        {"day": yesterday_iso, "steps": 11204},
    ])
    captured_urls = []

    async def fake_get(url, headers=None, **kwargs):
        captured_urls.append(url)
        return _mock_response(200, payload)

    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=fake_get)
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")

    assert resp.status_code == 200
    assert len(captured_urls) == 1
    url = captured_urls[0]
    assert f"start_date={yesterday_iso}" in url
    assert f"end_date={expected_end}" in url, (
        f"URL must request end_date={expected_end} (today+1 in London) to "
        f"include today's row. Got: {url}"
    )
    # Today's row was filtered correctly even though we asked for a wider window
    body = resp.json()
    assert body["step_count"] == 8432
    assert body["step_count_yesterday"] == 11204


def test_summary_zero_steps_propagates(_reset_state):
    _write_test_tokens(_reset_state)
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([
        {"day": today_iso, "steps": 0},
        {"day": yesterday_iso, "steps": 11204},
    ])
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response(200, payload))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")
    body = resp.json()
    assert body["step_count"] == 0
    assert body["step_count"] is not None


def test_summary_credentials_rotation_invalidates_tokens(_reset_state):
    # Write tokens with old client_id
    now = datetime.now(tz=timezone.utc)
    _reset_state.write_text(json.dumps({
        "access_token": "a", "refresh_token": "r",
        "expires_at": (now + timedelta(minutes=60)).isoformat(),
        "obtained_at": now.isoformat(),
        "client_id": "different-client-id",
    }))
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_not_connected"
    assert not _reset_state.exists()  # deleted on detection


def test_summary_data_fetch_5xx_with_cache_returns_stale(_reset_state):
    _write_test_tokens(_reset_state)
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([{"day": today_iso, "steps": 8432}])
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        # First call ok (populates cache), second call 500.
        instance.get = AsyncMock(side_effect=[
            _mock_response(200, payload),
            _mock_response(500, {}),
        ])
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            first = client.get("/api/widgets/oura/summary")
            assert first.json()["stale"] is False
            # Expire data cache
            oura_mod._data_cache["fetched_at"] = oura_mod._data_cache["fetched_at"].replace(
                year=oura_mod._data_cache["fetched_at"].year - 1
            )
            second = client.get("/api/widgets/oura/summary")
    assert second.status_code == 200
    body = second.json()
    assert body["stale"] is True
    assert body["step_count"] == 8432


def test_summary_data_fetch_401_triggers_refresh_and_retry(_reset_state):
    _write_test_tokens(_reset_state, expires_in_minutes=60)
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([{"day": today_iso, "steps": 8432}])

    get_calls = [
        _mock_response(401, {"detail": "Unauthorized"}),  # initial 401
        _mock_response(200, payload),                      # retry success
    ]
    post_calls = [
        _mock_response(200, {
            "access_token": "a-refreshed",
            "refresh_token": "r-rotated",
            "expires_in": 3600,
        }),
    ]

    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=get_calls)
        instance.post = AsyncMock(side_effect=post_calls)
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")

    assert resp.status_code == 200
    assert resp.json()["step_count"] == 8432
    # Refresh + retry: 1 POST + 2 GETs
    assert instance.post.await_count == 1
    assert instance.get.await_count == 2


def test_summary_data_fetch_401_after_retry_deletes_tokens(_reset_state):
    _write_test_tokens(_reset_state, expires_in_minutes=60)
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=[
            _mock_response(401, {}),
            _mock_response(401, {}),
        ])
        instance.post = AsyncMock(return_value=_mock_response(200, {
            "access_token": "a", "refresh_token": "r",
            "expires_in": 3600,
        }))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_token_invalid"
    assert not _reset_state.exists()


def test_summary_expired_access_token_refreshes(_reset_state):
    _write_test_tokens(_reset_state, expires_in_minutes=1)  # within refresh margin
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([{"day": today_iso, "steps": 7000}])

    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_mock_response(200, {
            "access_token": "a-new",
            "refresh_token": "r-new",
            "expires_in": 3600,
        }))
        instance.get = AsyncMock(return_value=_mock_response(200, payload))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")

    assert resp.status_code == 200
    assert instance.post.await_count == 1
    # Tokens file updated
    new_tokens = json.loads(_reset_state.read_text())
    assert new_tokens["access_token"] == "a-new"
    assert new_tokens["refresh_token"] == "r-new"
    assert new_tokens["client_id"] == CLIENT_ID


def test_summary_refresh_401_deletes_tokens(_reset_state):
    _write_test_tokens(_reset_state, expires_in_minutes=1)
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_mock_response(401, {}))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_token_invalid"
    assert not _reset_state.exists()


def test_summary_cache_hit_avoids_second_call(_reset_state):
    _write_test_tokens(_reset_state)
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([{"day": today_iso, "steps": 1}])
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response(200, payload))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            client.get("/api/widgets/oura/summary")
            client.get("/api/widgets/oura/summary")
    assert instance.get.await_count == 1


# ── /api/widgets/oura/oauth/start ──────────────────────────────────────────


def test_oauth_start_redirects_to_authorize_url():
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/oauth/start", follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert loc.startswith("https://cloud.ouraring.com/oauth/authorize?")
    assert f"client_id={CLIENT_ID}" in loc
    assert "scope=daily" in loc
    assert "state=" in loc
    assert "redirect_uri=" in loc


def test_oauth_start_state_verifies():
    from urllib.parse import unquote
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/oauth/start", follow_redirects=False)
    loc = resp.headers["location"]
    state = unquote(loc.split("state=")[1].split("&")[0])
    assert _verify_state(state) is True


def test_oauth_start_no_credentials_returns_503():
    get_settings().oura_client_id = ""
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/oauth/start", follow_redirects=False)
    assert resp.status_code == 503


# ── /api/widgets/oura/oauth/callback ───────────────────────────────────────


def test_oauth_callback_invalid_state_redirects_with_error():
    with TestClient(create_app()) as client:
        resp = client.get(
            "/api/widgets/oura/oauth/callback?code=abc&state=invalid",
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "oauth_error=oauth_state_invalid" in resp.headers["location"]


def test_oauth_callback_missing_state_redirects_with_error():
    with TestClient(create_app()) as client:
        resp = client.get(
            "/api/widgets/oura/oauth/callback?code=abc",
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "oauth_error=oauth_state_invalid" in resp.headers["location"]


def test_oauth_callback_valid_state_missing_code_redirects_with_error():
    state = _build_state()
    with TestClient(create_app()) as client:
        resp = client.get(
            f"/api/widgets/oura/oauth/callback?state={state}",
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "oauth_error=oauth_code_missing" in resp.headers["location"]


def test_oauth_callback_happy_path_writes_tokens_and_redirects(_reset_state):
    state = _build_state()
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_mock_response(200, {
            "access_token": "a-initial",
            "refresh_token": "r-initial",
            "expires_in": 3600,
        }))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get(
                f"/api/widgets/oura/oauth/callback?code=initial-code&state={state}",
                follow_redirects=False,
            )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/?connected=1")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "default-src 'none'" in resp.headers.get("Content-Security-Policy", "")
    # Tokens written to disk
    tokens = json.loads(_reset_state.read_text())
    assert tokens["access_token"] == "a-initial"
    assert tokens["refresh_token"] == "r-initial"
    assert tokens["client_id"] == CLIENT_ID


def test_oauth_callback_token_endpoint_4xx_redirects_with_error(_reset_state):
    state = _build_state()
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_mock_response(400, {"detail": "Bad request"}))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get(
                f"/api/widgets/oura/oauth/callback?code=bad&state={state}",
                follow_redirects=False,
            )
    assert resp.status_code == 303
    assert "oauth_error=token_exchange_failed" in resp.headers["location"]
    assert not _reset_state.exists()


def test_oauth_callback_network_error_redirects_with_error(_reset_state):
    state = _build_state()
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.post = AsyncMock(side_effect=httpx.ConnectError(
            "net gone", request=httpx.Request("POST", "http://x")
        ))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get(
                f"/api/widgets/oura/oauth/callback?code=c&state={state}",
                follow_redirects=False,
            )
    assert resp.status_code == 303
    assert "oauth_error=token_exchange_failed" in resp.headers["location"]


# ── /api/widgets/oura/oauth/disconnect ─────────────────────────────────────


def test_oauth_disconnect_deletes_tokens(_reset_state):
    _write_test_tokens(_reset_state)
    assert _reset_state.exists()
    with TestClient(create_app()) as client:
        resp = client.post("/api/widgets/oura/oauth/disconnect")
    assert resp.status_code == 200
    assert resp.json() == {"disconnected": True}
    assert not _reset_state.exists()


def test_oauth_disconnect_is_idempotent(_reset_state):
    assert not _reset_state.exists()
    with TestClient(create_app()) as client:
        resp = client.post("/api/widgets/oura/oauth/disconnect")
    assert resp.status_code == 200
    assert resp.json() == {"disconnected": True}


# ── Concurrent refresh — exactly ONE HTTP call fires ───────────────────────


@pytest.mark.asyncio
async def test_concurrent_refresh_fires_exactly_one_http(_reset_state):
    """Five concurrent _get_valid_access_token() calls → 1 refresh HTTP call."""
    _write_test_tokens(_reset_state, expires_in_minutes=1)  # forces refresh

    http_call_count = 0

    async def fake_post(url, data=None, **kwargs):
        nonlocal http_call_count
        http_call_count += 1
        # Tiny delay so concurrent waiters pile up on the lock
        await asyncio.sleep(0.01)
        return _mock_response(200, {
            "access_token": f"a-new-{http_call_count}",
            "refresh_token": f"r-new-{http_call_count}",
            "expires_in": 3600,
        })

    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.post = AsyncMock(side_effect=fake_post)
        ClientCls.return_value.__aenter__.return_value = instance

        results = await asyncio.gather(*[
            oura_mod._get_valid_access_token() for _ in range(5)
        ])

    # All 5 callers got the SAME access_token (the one from the single refresh)
    assert len(set(results)) == 1, f"Got {len(set(results))} different tokens"
    # Exactly one HTTP call to Oura's token endpoint
    assert http_call_count == 1


# ── Atomic write uses os.replace ───────────────────────────────────────────


def test_write_tokens_uses_os_replace(_reset_state, monkeypatch):
    """Pin that atomic write goes through os.replace (not plain open+write)."""
    calls = []
    original_replace = os.replace

    def spy_replace(src, dst):
        calls.append((str(src), str(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(oura_mod.os, "replace", spy_replace)
    oura_mod._write_tokens_atomic({
        "access_token": "a", "refresh_token": "r",
        "expires_at": "2026-06-22T12:00:00+00:00",
        "obtained_at": "2026-06-22T11:00:00+00:00",
        "client_id": CLIENT_ID,
    })
    assert len(calls) == 1
    src, dst = calls[0]
    assert src.endswith(".tmp")
    assert dst == str(_reset_state)
    # The final file should exist with correct content
    assert json.loads(_reset_state.read_text())["access_token"] == "a"
