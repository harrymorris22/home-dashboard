"""Coverage for the user-asserted window state route.

Mirror of test_api_blinds.py. Same shape, different actuator type.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models import ActuatorState
from app.db.session import session_scope
from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_post_writes_actuator_rows_with_source_manual():
    client = _client()
    resp = client.post("/api/windows/state", json={"mezzanine": True, "bedroom": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["windows"]["mezzanine"] is True
    assert body["windows"]["bedroom"] is False

    with session_scope() as session:
        rows = session.query(ActuatorState).all()
    actuators = sorted(r.actuator for r in rows)
    assert actuators == ["window:bedroom", "window:mezzanine"]
    assert all(r.source == "manual" for r in rows)
    # Values are stored as "open" / "closed" strings.
    by_actuator = {r.actuator: r.value for r in rows}
    assert by_actuator["window:mezzanine"] == "open"
    assert by_actuator["window:bedroom"] == "closed"


def test_post_partial_only_writes_specified_zones():
    """Posting one zone doesn't disturb the others (latest-per-zone view)."""
    client = _client()
    client.post(
        "/api/windows/state",
        json={
            "mezzanine": True,
            "downstairs": False,
            "ceiling_apex": True,
            "bedroom": False,
        },
    )
    # Now update just bedroom.
    resp = client.post("/api/windows/state", json={"bedroom": True})
    body = resp.json()
    assert body["windows"] == {
        "mezzanine": True,
        "downstairs": False,
        "ceiling_apex": True,
        "bedroom": True,
    }


def test_post_rejects_unknown_zone():
    client = _client()
    resp = client.post("/api/windows/state", json={"kitchen_skylight": True})
    assert resp.status_code == 422
    assert "unknown window zone" in resp.json()["detail"].lower()


def test_post_rejects_non_bool_value():
    """Pydantic schema enforces bool. Strings, ints, None all fail validation."""
    client = _client()
    for bad in ["open", 1, None, "true"]:
        resp = client.post("/api/windows/state", json={"mezzanine": bad})
        assert resp.status_code == 422, f"expected 422 for {bad!r}, got {resp.status_code}"


def test_post_rejects_empty_body():
    client = _client()
    resp = client.post("/api/windows/state", json={})
    assert resp.status_code == 422


def test_get_returns_latest_per_zone():
    client = _client()
    client.post("/api/windows/state", json={"mezzanine": True, "downstairs": False})
    resp = client.get("/api/windows/state")
    assert resp.status_code == 200
    assert resp.json()["windows"] == {"mezzanine": True, "downstairs": False}


def test_get_with_no_rows_returns_empty():
    client = _client()
    resp = client.get("/api/windows/state")
    assert resp.status_code == 200
    assert resp.json()["windows"] == {}


def test_bulk_all_closed_via_four_keys():
    """The frontend "ALL CLOSED" button sends every zone at once."""
    client = _client()
    resp = client.post(
        "/api/windows/state",
        json={
            "mezzanine": False,
            "downstairs": False,
            "ceiling_apex": False,
            "bedroom": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["windows"] == {
        "mezzanine": False,
        "downstairs": False,
        "ceiling_apex": False,
        "bedroom": False,
    }


def test_state_endpoint_picks_up_manual_input():
    """End-to-end: POST a manual state, then GET /api/state and confirm
    current_state.windows reflects it. This is the round-trip that makes the
    ActionPanel "currently open/closed" annotations appear for windows."""
    client = _client()
    client.post(
        "/api/windows/state",
        json={
            "mezzanine": True,
            "downstairs": False,
            "ceiling_apex": True,
            "bedroom": False,
        },
    )

    resp = client.get("/api/state")
    assert resp.status_code == 200
    state = resp.json()
    assert state["current_state"]["windows"] == {
        "mezzanine": True,
        "downstairs": False,
        "ceiling_apex": True,
        "bedroom": False,
    }
