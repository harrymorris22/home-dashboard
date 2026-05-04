from fastapi.testclient import TestClient

from app.main import create_app


def test_state_endpoint_returns_recommendations_with_no_weather():
    """No OWM key set in test env → weather=None → degraded mode, no crash."""
    app = create_app()
    client = TestClient(app)
    # Submit readings first.
    payload = {
        "zones": {
            "mezzanine":    {"temp_c": 24.0, "humidity_pct": 50, "lux_indoor": 5000},
            "downstairs":   {"temp_c": 22.0, "humidity_pct": 50},
            "ceiling_apex": {"temp_c": 26.0},
            "bedroom":      {"temp_c": 23.0, "humidity_pct": 55},
        },
    }
    client.post("/api/readings", json=payload)
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


def test_simulate_endpoint_walks_a_scenario():
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/simulate", json={"scenario_name": "hot_sunny_breeze"})
    assert resp.status_code == 200
    data = resp.json()
    rec = data["recommendations"]
    assert rec["by_blind_group"]["mezz"]["blind_pct"] == 100
    assert rec["by_zone"]["mezzanine"]["window_open"] is True


def test_simulate_lists_scenarios():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/simulate/scenarios")
    assert resp.status_code == 200
    names = resp.json()["scenarios"]
    assert "hot_sunny_breeze" in names
    assert "rain_override" in names


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


def test_history_returns_inserted_readings():
    app = create_app()
    client = TestClient(app)
    payload = {
        "zones": {
            "mezzanine":    {"temp_c": 24.0},
            "downstairs":   {"temp_c": 22.0},
            "ceiling_apex": {"temp_c": 26.0},
            "bedroom":      {"temp_c": 23.0},
        },
    }
    client.post("/api/readings", json=payload)
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
