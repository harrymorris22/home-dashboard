"""Climate widget proxy tests.

Covers happy path, cache hit, upstream failure → stale-cache fallback,
the no-cache-yet upstream-down path, and v0.4.0 office-temp + action helpers
(window/blind diff against current state with defensive shape handling)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.widgets import climate as climate_mod
from app.widgets.climate import (
    BLIND_ACTION_THRESHOLD,
    _blind_actions,
    _project,
    _window_actions,
)


UPSTREAM_OK = {
    "ts": "2026-05-20T12:00:00+00:00",
    "recommendations": {
        "global": {"scenario": "hot_sunny_breeze", "urgency": "amber"},
        "prompts": ["Open windows now"],
        "by_zone": {
            "mezzanine": {"window_open": True, "scenario": "hot_sunny"},
            "bedroom": {"window_open": False, "scenario": "comfortable"},
        },
        "by_blind_group": {
            "mezz": {"blind_pct": 30, "scenario": "hot_sunny"},
            "bedroom": {"blind_pct": 100, "scenario": "comfortable"},
        },
    },
    "sensors": {
        "mezzanine": {"temp_c": 24.5},
        "bedroom": {"temp_c": 22.0},
    },
    "current_state": {
        "windows": {"mezzanine": False, "bedroom": False},
        "blinds": {"mezz": 100, "bedroom": 100},
    },
}


def _mock_response(status: int = 200, json_data=UPSTREAM_OK) -> httpx.Response:
    return httpx.Response(status, json=json_data, request=httpx.Request("GET", "http://x"))


def _reset_cache():
    """Tests share module-level cache state; reset between tests."""
    climate_mod._cache["payload"] = None
    climate_mod._cache["fetched_at"] = None
    climate_mod._cache["stale"] = False


@pytest.fixture(autouse=True)
def _cache_reset():
    _reset_cache()
    yield
    _reset_cache()


# ── End-to-end proxy tests ──────────────────────────────────────────────────


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
    assert body["office_temp_c"] == 24.5
    assert body["prompt"] == "Open windows now"
    assert body["stale"] is False
    # Window: recommended True ≠ current False → "open mezzanine".
    assert {"zone": "mezzanine", "action": "open"} in body["window_actions"]
    # Bedroom: recommended False == current False → no action.
    assert all(a["zone"] != "bedroom" for a in body["window_actions"])
    # Blind: mezz target 30, current 100, delta 70 → "lower to 30".
    assert {
        "group": "mezz",
        "current_pct": 100,
        "target_pct": 30,
        "direction": "lower",
    } in body["blind_actions"]
    # Bedroom blind: target 100, current 100, delta 0 → no action.
    assert all(a["group"] != "bedroom" for a in body["blind_actions"])


def test_cache_hit_avoids_second_upstream_call():
    with patch.object(climate_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=_mock_response())
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            client.get("/api/widgets/climate")
            client.get("/api/widgets/climate")
    assert instance.get.await_count == 1


def test_upstream_failure_serves_stale_cache_with_new_fields():
    """Stale fallback must preserve v0.4.0 action arrays from the cached payload."""
    with patch.object(climate_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            side_effect=[
                _mock_response(),
                httpx.ConnectError("upstream gone", request=httpx.Request("GET", "http://x")),
            ]
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            first = client.get("/api/widgets/climate")
            assert first.json()["stale"] is False
            climate_mod._cache["fetched_at"] = climate_mod._cache["fetched_at"].replace(
                year=climate_mod._cache["fetched_at"].year - 1
            )
            second = client.get("/api/widgets/climate")
    assert second.status_code == 200
    body = second.json()
    assert body["stale"] is True
    assert body["scenario"] == "hot_sunny_breeze"
    assert body["office_temp_c"] == 24.5
    assert body["window_actions"] == [{"zone": "mezzanine", "action": "open"}]
    assert body["blind_actions"] == [
        {"group": "mezz", "current_pct": 100, "target_pct": 30, "direction": "lower"}
    ]


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


# ── _window_actions helper ──────────────────────────────────────────────────


def test_window_action_recommended_open_but_currently_closed():
    actions = _window_actions(
        {"mezzanine": {"window_open": True}},
        {"mezzanine": False},
    )
    assert actions == [{"zone": "mezzanine", "action": "open"}]


def test_window_action_recommended_close_but_currently_open():
    actions = _window_actions(
        {"bedroom": {"window_open": False}},
        {"bedroom": True},
    )
    assert actions == [{"zone": "bedroom", "action": "close"}]


def test_window_no_action_when_current_equals_recommended():
    actions = _window_actions(
        {"mezzanine": {"window_open": True}},
        {"mezzanine": True},
    )
    assert actions == []


def test_window_no_action_when_recommended_is_none():
    actions = _window_actions(
        {"mezzanine": {"window_open": None}},
        {"mezzanine": False},
    )
    assert actions == []


def test_window_no_action_when_current_state_missing_zone():
    """Partial overlap: by_zone has zone X, current_state.windows doesn't."""
    actions = _window_actions(
        {"mezzanine": {"window_open": True}},
        {},
    )
    assert actions == []


def test_window_skips_non_dict_recommendation():
    actions = _window_actions(
        {"mezzanine": "not a dict"},
        {"mezzanine": False},
    )
    assert actions == []


# ── _blind_actions helper ──────────────────────────────────────────────────


def test_blind_action_above_threshold_emits_lower():
    actions = _blind_actions(
        {"mezz": {"blind_pct": 30, "scenario": "hot_sunny"}},
        {"mezz": 100},
    )
    assert actions == [
        {"group": "mezz", "current_pct": 100, "target_pct": 30, "direction": "lower"}
    ]


def test_blind_action_above_threshold_emits_raise():
    actions = _blind_actions(
        {"mezz": {"blind_pct": 100, "scenario": "cold"}},
        {"mezz": 0},
    )
    assert actions == [
        {"group": "mezz", "current_pct": 0, "target_pct": 100, "direction": "raise"}
    ]


def test_blind_no_action_below_threshold():
    actions = _blind_actions(
        {"mezz": {"blind_pct": 95, "scenario": "comfortable"}},
        {"mezz": 100},
    )
    assert actions == []  # delta of 5 < threshold


def test_blind_action_at_exactly_threshold():
    """At delta == BLIND_ACTION_THRESHOLD the action surfaces (uses `<` not `<=`)."""
    actions = _blind_actions(
        {"mezz": {"blind_pct": 100 - BLIND_ACTION_THRESHOLD, "scenario": "warm"}},
        {"mezz": 100},
    )
    assert len(actions) == 1
    assert actions[0]["direction"] == "lower"


def test_blind_neutral_scenario_suppresses_even_if_delta_large():
    actions = _blind_actions(
        {"mezz": {"blind_pct": 30, "scenario": "neutral"}},
        {"mezz": 100},
    )
    assert actions == []


def test_blind_no_action_when_target_is_none():
    actions = _blind_actions(
        {"mezz": {"blind_pct": None, "scenario": "comfortable"}},
        {"mezz": 100},
    )
    assert actions == []


def test_blind_no_action_when_current_missing():
    actions = _blind_actions(
        {"mezz": {"blind_pct": 30, "scenario": "hot_sunny"}},
        {},
    )
    assert actions == []


# ── _project: defensive shape handling (schema drift / older upstream) ─────


def test_project_no_current_state_key_returns_empty_actions():
    state = {
        "ts": "2026-06-19T10:00:00Z",
        "recommendations": {"global": {"scenario": "hot_sunny", "urgency": "amber"}},
        "sensors": {"mezzanine": {"temp_c": 25.0}},
    }
    out = _project(state)
    assert out["window_actions"] == []
    assert out["blind_actions"] == []
    assert out["office_temp_c"] == 25.0


def test_project_empty_current_state_returns_empty_actions():
    state = {
        "ts": "2026-06-19T10:00:00Z",
        "recommendations": {
            "global": {"scenario": "hot_sunny", "urgency": "amber"},
            "by_zone": {"mezzanine": {"window_open": True}},
        },
        "sensors": {"mezzanine": {"temp_c": 25.0}},
        "current_state": {},
    }
    out = _project(state)
    assert out["window_actions"] == []
    assert out["blind_actions"] == []


def test_project_by_zone_none_returns_empty_actions():
    state = {
        "ts": "2026-06-19T10:00:00Z",
        "recommendations": {
            "global": {"scenario": "hot_sunny", "urgency": "amber"},
            "by_zone": None,
            "by_blind_group": None,
        },
        "sensors": {"mezzanine": {"temp_c": 25.0}},
        "current_state": {"windows": {"mezzanine": True}, "blinds": {"mezz": 50}},
    }
    out = _project(state)
    assert out["window_actions"] == []
    assert out["blind_actions"] == []


def test_project_mezzanine_sensor_missing():
    state = {
        "ts": "2026-06-19T10:00:00Z",
        "recommendations": {"global": {"scenario": "hot_sunny", "urgency": "amber"}},
        "sensors": {"bedroom": {"temp_c": 22.0}},
    }
    assert _project(state)["office_temp_c"] is None


def test_project_mezzanine_sensor_none_value_does_not_crash():
    """Defensive: sensors.get('mezzanine') returns None, not a dict."""
    state = {
        "ts": "2026-06-19T10:00:00Z",
        "recommendations": {"global": {"scenario": "hot_sunny", "urgency": "amber"}},
        "sensors": {"mezzanine": None},
    }
    assert _project(state)["office_temp_c"] is None


def test_project_minimal_payload_does_not_crash():
    """Worst case: upstream returns nearly nothing. Tile gets sane defaults."""
    out = _project({})
    assert out["scenario"] == "unknown"
    assert out["urgency"] == "green"
    assert out["office_temp_c"] is None
    assert out["window_actions"] == []
    assert out["blind_actions"] == []
    assert out["prompt"] is None
