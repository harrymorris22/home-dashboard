"""Coverage for /api/outdoor/bias (v0.20.0)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import repo
from app.db.models import OutdoorBiasCalibration
from app.db.session import session_scope
from app.main import create_app


def _seed_calibration(bias=None, samples=None, days=30):
    row = OutdoorBiasCalibration(
        fitted_at=datetime.now(tz=timezone.utc),
        days_window=days,
        bias_by_hour_json=json.dumps(bias or [1.5] * 24),
        sample_counts_json=json.dumps(samples or [7] * 24),
    )
    with session_scope() as session:
        repo.insert_outdoor_calibration(session, row)
        session.commit()


def test_get_bias_empty_returns_null_with_settings():
    client = TestClient(create_app())
    resp = client.get("/api/outdoor/bias")
    assert resp.status_code == 200
    body = resp.json()
    assert body["calibration"] is None
    # Settings always present so the UI can render its mode + knobs.
    assert body["settings"]["correction"] in ("sensor_only", "sensor_bias_corrected")
    assert body["settings"]["microclimate_baseline_c"] == 1.5
    assert body["settings"]["clearness_floor"] == 0.15


def test_get_bias_returns_latest_row():
    bias = [i / 10 for i in range(24)]
    _seed_calibration(bias=bias, samples=[7] * 24, days=14)
    client = TestClient(create_app())
    resp = client.get("/api/outdoor/bias")
    assert resp.status_code == 200
    cal = resp.json()["calibration"]
    assert cal is not None
    assert cal["bias_by_hour"] == bias
    assert cal["days_window"] == 14
    assert cal["sample_counts"] == [7] * 24


def test_get_bias_returns_only_latest_when_multiple():
    _seed_calibration(bias=[0.0] * 24, days=7)
    _seed_calibration(bias=[9.9] * 24, days=30)
    client = TestClient(create_app())
    resp = client.get("/api/outdoor/bias")
    cal = resp.json()["calibration"]
    assert cal["days_window"] == 30
    assert cal["bias_by_hour"] == [9.9] * 24


def test_post_bias_fails_cleanly_without_ha_or_config(monkeypatch):
    """POST returns a structured error rather than 500-ing when the HA
    client isn't available or the outdoor sensor entity isn't configured.
    Either 400 (no entity) or 503 (no client) is acceptable — both are
    valid guards that the calibrator can't run."""
    client = TestClient(create_app())
    resp = client.post("/api/outdoor/bias")
    assert resp.status_code in (400, 503)
    assert "detail" in resp.json()
