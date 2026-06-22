"""Oura widget proxy tests.

Covers happy path, cache, stale-fallback, 401-distinct-error, whitespace
token, non-JSON body, 0-vs-null step counts, _project filter, and DST-safe
date helpers. Mirrors test_calendar.py httpx-mock pattern + test_climate_proxy
cache-reset fixture."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import get_settings
from app.widgets import oura as oura_mod
from app.widgets.oura import _london_today_yesterday, _project


TOKEN = "test-pat-token-12345"


def _mock_response(status: int = 200, json_data=None) -> httpx.Response:
    return httpx.Response(
        status,
        json=json_data if json_data is not None else {"data": []},
        request=httpx.Request("GET", "http://x"),
    )


def _make_oura_payload(days: list[dict]) -> dict:
    return {"data": days, "next_token": None}


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level cache + settings token between tests."""
    oura_mod._cache["payload"] = None
    oura_mod._cache["fetched_at"] = None
    oura_mod._cache["stale"] = False
    get_settings().oura_pat_token = TOKEN
    yield
    oura_mod._cache["payload"] = None
    oura_mod._cache["fetched_at"] = None
    get_settings().oura_pat_token = ""


# ── End-to-end proxy tests ──────────────────────────────────────────────────


def test_happy_path_returns_today_and_yesterday():
    """Mock Oura response with both days; assert payload + Bearer header sent."""
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([
        {"day": yesterday_iso, "steps": 11204},
        {"day": today_iso, "steps": 8432},
    ])
    captured_headers = {}

    async def fake_get(url, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return _mock_response(200, payload)

    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=fake_get)
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["step_count"] == 8432
    assert body["step_count_yesterday"] == 11204
    assert body["stale"] is False
    assert "last_success_at" in body
    # Bearer header sent with exact format
    assert captured_headers.get("Authorization") == f"Bearer {TOKEN}"


def test_empty_token_returns_503_unconfigured():
    get_settings().oura_pat_token = ""
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_pat_token_not_configured"
    assert "cloud.ouraring.com" in resp.json()["detail"]["instruction"]


def test_whitespace_only_token_treated_as_unconfigured():
    get_settings().oura_pat_token = "   \n  "
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_pat_token_not_configured"


def test_401_returns_distinct_token_invalid_error():
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response(401, {"detail": "Unauthorized"}))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "oura_token_invalid"
    assert "revoked or" in resp.json()["detail"]["instruction"]


def test_500_with_cached_payload_returns_stale():
    """Prime cache, then upstream 500 → stale fallback preserves counts."""
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([
        {"day": yesterday_iso, "steps": 5000},
        {"day": today_iso, "steps": 7000},
    ])
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            side_effect=[_mock_response(200, payload), _mock_response(500, {})]
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            first = client.get("/api/widgets/oura/summary")
            assert first.json()["stale"] is False
            # Force cache expiry
            oura_mod._cache["fetched_at"] = oura_mod._cache["fetched_at"].replace(
                year=oura_mod._cache["fetched_at"].year - 1
            )
            second = client.get("/api/widgets/oura/summary")
    assert second.status_code == 200
    body = second.json()
    assert body["stale"] is True
    assert body["step_count"] == 7000
    assert body["step_count_yesterday"] == 5000


def test_500_no_cache_returns_502_fetch_failed():
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response(500, {}))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"] == "oura_fetch_failed"


def test_connection_error_with_cached_payload_returns_stale():
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([
        {"day": today_iso, "steps": 100},
    ])
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            side_effect=[
                _mock_response(200, payload),
                httpx.ConnectError("net gone", request=httpx.Request("GET", "http://x")),
            ]
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            client.get("/api/widgets/oura/summary")
            oura_mod._cache["fetched_at"] = oura_mod._cache["fetched_at"].replace(
                year=oura_mod._cache["fetched_at"].year - 1
            )
            second = client.get("/api/widgets/oura/summary")
    assert second.status_code == 200
    assert second.json()["stale"] is True
    assert second.json()["step_count"] == 100


def test_cache_hit_avoids_second_upstream_call():
    today_iso, _ = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([{"day": today_iso, "steps": 1}])
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response(200, payload))
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            client.get("/api/widgets/oura/summary")
            client.get("/api/widgets/oura/summary")
    assert instance.get.await_count == 1


def test_non_json_body_returns_502_without_500():
    """Oura's CDN occasionally serves HTML errors with 200."""
    bad_resp = httpx.Response(
        200,
        content=b"<html>error page</html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", "http://x"),
    )
    with patch.object(oura_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=bad_resp)
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/oura/summary")
    # No cache → falls through to 502 fetch_failed (not 500)
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"] == "oura_fetch_failed"


def test_zero_steps_renders_as_zero_not_null():
    """0 is a valid step count (early morning), distinct from None."""
    today_iso, yesterday_iso = _london_today_yesterday(datetime.now(tz=timezone.utc))
    payload = _make_oura_payload([
        {"day": today_iso, "steps": 0},
        {"day": yesterday_iso, "steps": 11000},
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
    assert body["step_count_yesterday"] == 11000


# ── _project unit tests ────────────────────────────────────────────────────


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
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] is None
    assert out["step_count_yesterday"] == 11204


def test_project_neither_day_present():
    out = _project(
        _make_oura_payload([{"day": "2026-06-15", "steps": 7000}]),
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] is None
    assert out["step_count_yesterday"] is None


def test_project_empty_data():
    out = _project(
        _make_oura_payload([]),
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] is None
    assert out["step_count_yesterday"] is None


def test_project_filters_extra_days():
    """Oura sometimes returns adjacent days — only pick the two requested."""
    out = _project(
        _make_oura_payload([
            {"day": "2026-06-19", "steps": 1000},
            {"day": "2026-06-20", "steps": 2000},
            {"day": "2026-06-21", "steps": 3000},
            {"day": "2026-06-22", "steps": 4000},
            {"day": "2026-06-23", "steps": 5000},
        ]),
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] == 4000
    assert out["step_count_yesterday"] == 3000


def test_project_row_missing_steps_key_returns_none():
    out = _project(
        _make_oura_payload([{"day": "2026-06-22"}]),  # no "steps"
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] is None


def test_project_non_dict_row_skipped():
    out = _project(
        {"data": [
            "not a dict",
            None,
            {"day": "2026-06-22", "steps": 5000},
        ]},
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] == 5000


def test_project_zero_step_value_propagates():
    out = _project(
        _make_oura_payload([{"day": "2026-06-22", "steps": 0}]),
        today_iso="2026-06-22",
        yesterday_iso="2026-06-21",
    )
    assert out["step_count"] == 0
    assert out["step_count"] is not None


def test_project_data_field_missing_or_none():
    assert _project({}, "2026-06-22", "2026-06-21")["step_count"] is None
    assert _project({"data": None}, "2026-06-22", "2026-06-21")["step_count"] is None


# ── _london_today_yesterday unit tests ──────────────────────────────────────


def test_london_today_midday_utc():
    """UTC noon = London 1pm (BST) or noon (GMT). Today is the same date."""
    now_utc = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now_utc)
    assert today == "2026-06-22"
    assert yesterday == "2026-06-21"


def test_london_today_late_evening_utc_in_summer():
    """22:30 UTC in June = 23:30 BST — still 'today' in London."""
    now_utc = datetime(2026, 6, 22, 22, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now_utc)
    assert today == "2026-06-22"
    assert yesterday == "2026-06-21"


def test_london_today_after_midnight_utc_in_summer():
    """01:30 UTC in June = 02:30 BST — already the next day in London."""
    now_utc = datetime(2026, 6, 23, 1, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now_utc)
    assert today == "2026-06-23"
    assert yesterday == "2026-06-22"


def test_london_today_just_before_midnight_utc_in_summer():
    """23:00 UTC in June = 00:00 BST next day in London."""
    now_utc = datetime(2026, 6, 22, 23, 0, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now_utc)
    assert today == "2026-06-23"
    assert yesterday == "2026-06-22"


def test_london_today_spring_forward():
    """BST starts last Sunday of March. 02:30 BST = 01:30 UTC, still that day."""
    # 30 March 2026, 02:30 BST = 01:30 UTC
    now_utc = datetime(2026, 3, 30, 1, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now_utc)
    assert today == "2026-03-30"
    assert yesterday == "2026-03-29"


def test_london_today_autumn_back():
    """BST ends last Sunday of October. 01:30 GMT = 01:30 UTC, still that day."""
    # 26 October 2026, 01:30 GMT = 01:30 UTC
    now_utc = datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc)
    today, yesterday = _london_today_yesterday(now_utc)
    assert today == "2026-10-26"
    assert yesterday == "2026-10-25"
