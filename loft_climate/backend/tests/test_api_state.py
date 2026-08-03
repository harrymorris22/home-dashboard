"""Coverage for the API surface that survived v0.6.0.

The Entry + Simulate routes are gone; readings now land via the
slow-tick HA snapshot path. These tests exercise the read side of
that path: /api/state, /api/history, /api/config, /healthz.

Setup writes Reading rows directly via the repo (the v0.6 production
path is PushScheduler._tick_slow → repo.insert_reading_batch).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import repo
from app.db.models import Reading
from app.db.session import session_scope
from app.main import create_app


def _seed_readings():
    """Mimic what the slow-tick snapshot task writes."""
    now = datetime.now(tz=timezone.utc)
    rows = [
        Reading(ts=now, zone="mezzanine", temp_c=24.0, humidity_pct=50.0,
                lux_indoor=5000.0, source="ha"),
        Reading(ts=now, zone="downstairs", temp_c=22.0, humidity_pct=50.0,
                lux_indoor=None, source="ha"),
        Reading(ts=now, zone="ceiling_apex", temp_c=26.0, humidity_pct=None,
                lux_indoor=None, source="ha"),
        Reading(ts=now, zone="bedroom", temp_c=23.0, humidity_pct=55.0,
                lux_indoor=None, source="ha"),
    ]
    with session_scope() as session:
        repo.insert_reading_batch(session, rows)
        session.commit()


def test_state_endpoint_returns_recommendations_with_no_weather():
    """No OWM key set in test env → weather=None → degraded mode, no crash."""
    _seed_readings()
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["weather"] is None
    assert "recommendations" in data
    rec = data["recommendations"]
    assert "global" in rec
    assert "by_blind_group" in rec
    assert "by_zone" in rec
    # Offline banner prompt expected.
    assert any("offline" in p.lower() for p in rec["prompts"])


def test_state_outdoor_block_present_when_offline():
    """v0.21: /api/state always includes the outdoor breakdown, even when
    Met.no is offline and no sensor is configured. All four fields must be
    present so the frontend can render None safely."""
    _seed_readings()
    client = TestClient(create_app())
    body = client.get("/api/state").json()
    assert "outdoor" in body
    for key in ("effective_c", "raw_c", "forecast_c", "delta_c"):
        assert key in body["outdoor"], f"outdoor missing {key!r}"
    # In the offline test env everything should be None.
    assert body["outdoor"]["effective_c"] is None
    assert body["outdoor"]["raw_c"] is None
    assert body["outdoor"]["forecast_c"] is None
    assert body["outdoor"]["delta_c"] is None


def test_config_get_and_put_roundtrip():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/config")
    assert resp.status_code == 200
    cfg = resp.json()
    cfg["zones"]["bedroom"]["comfort_max"] = 23.0
    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200


def test_config_put_invariant_violation_returns_422():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/config")
    cfg = resp.json()
    cfg["zones"]["mezzanine"]["comfort_min"] = 30.0
    cfg["zones"]["mezzanine"]["comfort_max"] = 20.0
    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 422


def test_history_returns_seeded_readings():
    """History reads from the readings table — populated in v0.6 by the
    slow-tick snapshot path. Setup writes rows directly via repo.
    """
    _seed_readings()
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) >= 4


def test_healthz():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/healthz")
    body = resp.json()
    assert body["ok"] is True
    # HA not configured in tests → not connected.
    assert body.get("ha_connected") is False
