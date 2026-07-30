"""Coverage for /api/weather/history (v0.19.0).

Motivating scenario: user needs to calibrate the SwitchBot outdoor sensor
against Met.no readings. HA Recorder has SwitchBot history; the add-on's
weather_cache table has Met.no history. This endpoint exposes the latter
so an external plot/notebook can align the two.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import repo
from app.db.models import WeatherCache
from app.db.session import session_scope
from app.main import create_app


def _seed_weather(fetched_at: datetime, temp_c: float, feels_like_c: float | None = None):
    payload = {
        "fetched_at": fetched_at.isoformat(),
        "temp_c": temp_c,
        "feels_like_c": feels_like_c if feels_like_c is not None else temp_c,
        "humidity_pct": 55.0,
        "cloud_cover_pct": 40.0,
        "wind_speed_mps": 2.5,
        "wind_gust_mps": None,
        "uvi": 3.0,
        "conditions": "Clouds",
        "precip_now": False,
        "sunrise": (fetched_at - timedelta(hours=6)).isoformat(),
        "sunset": (fetched_at + timedelta(hours=8)).isoformat(),
        "hourly": [],
    }
    row = WeatherCache(fetched_at=fetched_at, payload_json=json.dumps(payload))
    with session_scope() as session:
        repo.insert_weather(session, row)
        session.commit()


def test_history_returns_points_in_range():
    now = datetime.now(tz=timezone.utc)
    _seed_weather(now - timedelta(hours=1), 24.5)
    _seed_weather(now - timedelta(hours=2), 24.0)
    _seed_weather(now - timedelta(hours=3), 23.5)
    client = TestClient(create_app())
    resp = client.get("/api/weather/history?days=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 3
    # oldest first
    temps = [p["temp_c"] for p in body["points"]]
    assert temps[-3:] == [23.5, 24.0, 24.5]
    # every field surfaced
    p = body["points"][-1]
    for key in ("ts", "temp_c", "feels_like_c", "humidity_pct",
                "cloud_cover_pct", "wind_speed_mps", "uvi",
                "conditions", "precip_now"):
        assert key in p


def test_history_days_param_clamped_to_window():
    """Rows older than the requested window must NOT appear."""
    now = datetime.now(tz=timezone.utc)
    _seed_weather(now - timedelta(days=10), 15.0)  # outside window
    _seed_weather(now - timedelta(hours=2), 24.0)  # inside window
    client = TestClient(create_app())
    resp = client.get("/api/weather/history?days=1")
    body = resp.json()
    temps = [p["temp_c"] for p in body["points"]]
    assert 15.0 not in temps
    assert 24.0 in temps


def test_history_rejects_days_over_cap():
    """90 days is the hard cap; 91 should 422."""
    client = TestClient(create_app())
    resp = client.get("/api/weather/history?days=91")
    assert resp.status_code == 422


def test_history_rejects_zero_days():
    client = TestClient(create_app())
    resp = client.get("/api/weather/history?days=0")
    assert resp.status_code == 422


def test_history_skips_corrupt_rows():
    """A row with unparseable payload_json must not fail the whole window."""
    now = datetime.now(tz=timezone.utc)
    _seed_weather(now - timedelta(hours=1), 24.0)
    with session_scope() as session:
        session.add(WeatherCache(fetched_at=now - timedelta(hours=2), payload_json="{not json"))
        session.commit()
    client = TestClient(create_app())
    resp = client.get("/api/weather/history?days=1")
    assert resp.status_code == 200
    temps = [p["temp_c"] for p in resp.json()["points"]]
    assert 24.0 in temps


def test_history_empty_when_no_rows():
    client = TestClient(create_app())
    resp = client.get("/api/weather/history?days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["points"] == []
