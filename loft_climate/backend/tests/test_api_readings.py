from fastapi.testclient import TestClient

from app.main import create_app


def test_post_readings_inserts_all_zones():
    app = create_app()
    client = TestClient(app)
    payload = {
        "ts": "2026-05-01T15:30:00+00:00",
        "zones": {
            "mezzanine":    {"temp_c": 24.0, "humidity_pct": 50, "lux_indoor": 8000},
            "downstairs":   {"temp_c": 22.0, "humidity_pct": 50},
            "ceiling_apex": {"temp_c": 26.0},
            "bedroom":      {"temp_c": 23.0, "humidity_pct": 55, "lux_indoor": 5000},
        },
    }
    resp = client.post("/api/readings", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["ids"]) == 4
    assert data["feedback_id"] is None


def test_post_readings_with_feedback():
    app = create_app()
    client = TestClient(app)
    payload = {
        "zones": {
            "mezzanine":    {"temp_c": 24.0},
            "downstairs":   {"temp_c": 22.0},
            "ceiling_apex": {"temp_c": 26.0},
            "bedroom":      {"temp_c": 23.0},
        },
        "feedback": {"action_taken": "closed bedroom blind", "felt_right": "yes"},
    }
    resp = client.post("/api/readings", json=payload)
    assert resp.status_code == 201
    assert resp.json()["feedback_id"] is not None


def test_get_latest_returns_most_recent():
    app = create_app()
    client = TestClient(app)
    p1 = {
        "ts": "2026-05-01T10:00:00+00:00",
        "zones": {z: {"temp_c": 20.0} for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")},
    }
    p2 = {
        "ts": "2026-05-01T15:00:00+00:00",
        "zones": {z: {"temp_c": 25.0} for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")},
    }
    client.post("/api/readings", json=p1)
    client.post("/api/readings", json=p2)
    resp = client.get("/api/readings/latest")
    assert resp.status_code == 200
    data = resp.json()["zones"]
    for zone in ("mezzanine", "downstairs", "ceiling_apex", "bedroom"):
        assert data[zone]["temp_c"] == 25.0
