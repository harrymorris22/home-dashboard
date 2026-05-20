"""System widget tests.

Happy path, thermal-file-missing graceful degradation (critical-gap test),
empty UptimeSamples → null aggregates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.models import UptimeSample
from app.db.session import session_scope
from app.main import create_app
from app.widgets import system as system_mod


def test_happy_path_returns_expected_shape():
    with patch.object(system_mod, "_read_thermal_zone", return_value=42.5):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/system/health")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("cpu_pct", "cpu_temp_c", "disk_pct", "mem_pct", "internet_24h_pct", "lan_24h_pct", "last_ping_ts"):
        assert key in body
    assert body["cpu_temp_c"] == 42.5


def test_thermal_file_missing_returns_none(monkeypatch):
    """CRITICAL — guards the Pi-vs-amd64 silent-crash failure mode.

    On non-Pi hardware (developer's Mac, Intel HA box), the thermal sysfs
    path doesn't exist. The widget must return None, not 500.
    """
    # _read_thermal_zone reads from THERMAL_PATH; point it at a non-existent file.
    from pathlib import Path
    monkeypatch.setattr(system_mod, "THERMAL_PATH", Path("/nonexistent/thermal"))
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/system/health")
    assert resp.status_code == 200
    assert resp.json()["cpu_temp_c"] is None


def test_no_uptime_samples_returns_null_aggregates():
    with patch.object(system_mod, "_read_thermal_zone", return_value=None):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/system/health")
    body = resp.json()
    assert body["internet_24h_pct"] is None
    assert body["lan_24h_pct"] is None
    assert body["last_ping_ts"] is None


def test_aggregates_internet_vs_lan_buckets():
    """1.1.1.1 + 8.8.8.8 = internet bucket. Anything else = LAN bucket."""
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        session.add_all([
            UptimeSample(ts=now - timedelta(minutes=1), target="1.1.1.1", success=True, latency_ms=10),
            UptimeSample(ts=now - timedelta(minutes=2), target="1.1.1.1", success=True, latency_ms=10),
            UptimeSample(ts=now - timedelta(minutes=3), target="8.8.8.8", success=False, latency_ms=None),
            UptimeSample(ts=now - timedelta(minutes=4), target="8.8.8.8", success=True, latency_ms=15),
            UptimeSample(ts=now - timedelta(minutes=5), target="192.168.1.1", success=True, latency_ms=2),
            UptimeSample(ts=now - timedelta(minutes=6), target="192.168.1.1", success=True, latency_ms=3),
        ])

    with patch.object(system_mod, "_read_thermal_zone", return_value=None):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/system/health")

    body = resp.json()
    # Internet: 3/4 success = 75%
    assert body["internet_24h_pct"] == pytest.approx(75.0, abs=0.1)
    # LAN: 2/2 = 100%
    assert body["lan_24h_pct"] == pytest.approx(100.0, abs=0.1)
    assert body["last_ping_ts"] is not None


def test_samples_older_than_24h_excluded():
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        session.add_all([
            # Old sample, should be excluded.
            UptimeSample(ts=now - timedelta(hours=25), target="1.1.1.1", success=False, latency_ms=None),
            # Recent sample, should be included.
            UptimeSample(ts=now - timedelta(minutes=5), target="1.1.1.1", success=True, latency_ms=10),
        ])

    with patch.object(system_mod, "_read_thermal_zone", return_value=None):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/system/health")

    body = resp.json()
    # Only the recent (success) sample counted.
    assert body["internet_24h_pct"] == pytest.approx(100.0, abs=0.1)
