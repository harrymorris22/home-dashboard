"""Climate widget proxy tests.

Covers happy path, cache hit, upstream failure → stale-cache fallback,
and the no-cache-yet upstream-down path."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.widgets import climate as climate_mod


UPSTREAM_OK = {
    "ts": "2026-05-20T12:00:00+00:00",
    "recommendations": {
        "global": {"scenario": "hot_sunny_breeze", "urgency": "amber"},
        "prompts": ["Open windows now"],
    },
    "sensors": {"bedroom": {"temp_c": 24.5}},
}


def _mock_response(status: int = 200, json_data=UPSTREAM_OK) -> httpx.Response:
    return httpx.Response(status, json=json_data, request=httpx.Request("GET", "http://x"))


def test_happy_path_projects_state_to_summary():
    with patch.object(climate_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response())
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/climate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] == "hot_sunny_breeze"
    assert body["urgency"] == "amber"
    assert body["bedroom_temp_c"] == 24.5
    assert body["prompt"] == "Open windows now"
    assert body["stale"] is False


def test_cache_hit_avoids_second_upstream_call():
    with patch.object(climate_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response())
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            client.get("/api/widgets/climate")
            client.get("/api/widgets/climate")  # second call should hit cache
    # Only one upstream HTTP call across both requests.
    assert instance.get.await_count == 1


def test_upstream_failure_serves_stale_cache():
    """Eng-review 1B regression: when upstream 5xxs, return last good payload
    with stale=true instead of an error."""
    with patch.object(climate_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        # First call ok, second call raises.
        instance.get = AsyncMock(
            side_effect=[
                _mock_response(),
                httpx.ConnectError("upstream gone", request=httpx.Request("GET", "http://x")),
            ]
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            # Prime the cache.
            first = client.get("/api/widgets/climate")
            assert first.json()["stale"] is False
            # Expire the cache window manually so we re-call upstream.
            climate_mod._cache["fetched_at"] = climate_mod._cache["fetched_at"].replace(
                year=climate_mod._cache["fetched_at"].year - 1
            )
            second = client.get("/api/widgets/climate")
    assert second.status_code == 200
    body = second.json()
    assert body["stale"] is True
    assert body["scenario"] == "hot_sunny_breeze"


def test_no_cache_and_upstream_down_returns_503():
    with patch.object(climate_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            side_effect=httpx.ConnectError("no upstream", request=httpx.Request("GET", "http://x"))
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/climate")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "climate_upstream_unreachable"
