"""Coverage for the user-asserted blind state route."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import repo
from app.db.models import ActuatorState
from app.db.session import session_scope
from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_post_writes_actuator_rows_with_source_manual():
    client = _client()
    resp = client.post("/api/blinds/state", json={"mezz": 0, "bedroom": 100})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["blinds"]["mezz"] == 0
    assert body["blinds"]["bedroom"] == 100

    with session_scope() as session:
        rows = session.query(ActuatorState).all()
    actuators = sorted(r.actuator for r in rows)
    assert actuators == ["blind:bedroom", "blind:mezz"]
    assert all(r.source == "manual" for r in rows)


def test_post_partial_only_writes_specified_groups():
    """Posting one group doesn't disturb the others (latest-per-group view)."""
    client = _client()
    client.post("/api/blinds/state", json={"mezz": 0, "downstairs": 100, "bedroom": 50})
    # Now update just bedroom.
    resp = client.post("/api/blinds/state", json={"bedroom": 0})
    body = resp.json()
    # All three groups still reflected; bedroom is the freshest.
    assert body["blinds"] == {"mezz": 0, "downstairs": 100, "bedroom": 0}


def test_post_rejects_unknown_group():
    client = _client()
    resp = client.post("/api/blinds/state", json={"loft_skylight": 50})
    assert resp.status_code == 422
    assert "unknown blind group" in resp.json()["detail"].lower()


def test_post_rejects_out_of_range():
    client = _client()
    resp = client.post("/api/blinds/state", json={"mezz": 150})
    assert resp.status_code == 422
    resp = client.post("/api/blinds/state", json={"mezz": -1})
    assert resp.status_code == 422


def test_post_rejects_empty_body():
    client = _client()
    resp = client.post("/api/blinds/state", json={})
    assert resp.status_code == 422


def test_get_returns_latest_per_group():
    client = _client()
    client.post("/api/blinds/state", json={"mezz": 0, "downstairs": 100})
    resp = client.get("/api/blinds/state")
    assert resp.status_code == 200
    assert resp.json()["blinds"] == {"mezz": 0, "downstairs": 100}


def test_get_with_no_rows_returns_empty():
    client = _client()
    resp = client.get("/api/blinds/state")
    assert resp.status_code == 200
    assert resp.json()["blinds"] == {}


def test_bulk_all_down_via_three_keys():
    """The frontend "ALL DOWN" button sends every group at once."""
    client = _client()
    resp = client.post(
        "/api/blinds/state",
        json={"mezz": 100, "downstairs": 100, "bedroom": 100},
    )
    assert resp.status_code == 200
    assert resp.json()["blinds"] == {"mezz": 100, "downstairs": 100, "bedroom": 100}


def test_state_endpoint_picks_up_manual_input():
    """End-to-end: POST a manual state, then GET /api/state and confirm
    current_state.blinds reflects it. This is the round-trip that makes the
    "blind state unknown" banner disappear in practice."""
    client = _client()
    client.post("/api/blinds/state", json={"mezz": 0, "downstairs": 100, "bedroom": 0})

    resp = client.get("/api/state")
    assert resp.status_code == 200
    state = resp.json()
    assert state["current_state"]["blinds"] == {
        "mezz": 0,
        "downstairs": 100,
        "bedroom": 0,
    }
