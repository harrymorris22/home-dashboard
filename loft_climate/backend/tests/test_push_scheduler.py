"""Coverage for PushScheduler additions in v0.6.0.

Two new responsibilities ride on the existing slow tick: HA → DB
snapshot persistence (so History accumulates real data without manual
entry) and a daily retention janitor (so SQLite doesn't grow forever).

These tests pin the behaviour we decided in plan-eng-review 1B + the
TODO-1 promotion: persistence failures must not break push dispatch,
and the janitor must be idempotent across same-day ticks.

Plus a smoke check that the four endpoints we deleted in v0.6.0 truly
left the build (guards against accidental re-mount in main.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import repo
from app.db.models import ActuatorState, Reading, Sunshine
from app.db.session import session_scope
from app.engine.types import (
    DashboardRecommendation,
    GlobalSummary,
    Snapshot,
)
from app.main import app
from app.push.scheduler import PushScheduler, _prune_old_rows
from app.sensors.source import ZoneSensorReading
from app.snapshot.service import StateBundle


# --- Helpers ---------------------------------------------------------------


def _bundle(cfg) -> StateBundle:
    """Minimal bundle with 4 zones + sunshine + 3 blinds."""
    from app.sun.calculator import SunPosition

    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    zones = {
        z: ZoneSensorReading(
            zone=z, ts=now, temp_c=22.0, humidity_pct=50.0, lux_indoor=None
        )
        for z in ("mezzanine", "downstairs", "ceiling_apex", "bedroom")
    }
    snap = Snapshot(
        now=now,
        zones=zones,
        weather=None,
        sun=SunPosition(
            elevation_deg=30.0,
            azimuth_deg=180.0,
            sunrise=now - timedelta(hours=7),
            sunset=now + timedelta(hours=8),
            is_daylight=True,
        ),
        config=cfg,
        sw_lux=10000.0,
        current_blind={"mezz": 50, "downstairs": 0, "bedroom": 100},
        current_window={},
    )
    rec = DashboardRecommendation(
        ts=now,
        by_blind_group={},
        by_zone={},
        global_=GlobalSummary(scenario="test", urgency="green"),
        prompts=[],
        rule_errors=[],
    )
    return StateBundle(cfg=cfg, snap=snap, rec=rec, next_actions=[])


@dataclass
class FakeVapid:
    public_key_b64url: str = "x"
    private_key_b64url: str = "y"
    subject: str = "mailto:test@example.com"


# --- Persistence tests -----------------------------------------------------


@pytest.mark.asyncio
async def test_slow_tick_persists_snapshot_rows(cfg):
    """After a slow tick, readings/sunshine/actuator_state rows exist."""
    sched = PushScheduler(ha_client=None, vapid_provider=lambda: FakeVapid())

    fake_bundle = _bundle(cfg)

    with patch(
        "app.push.scheduler.build_full_state",
        new=AsyncMock(return_value=fake_bundle),
    ), patch.object(sched, "_dispatch_decisions", AsyncMock()), patch.object(
        sched, "_staleness_recovery", AsyncMock()
    ):
        await sched._tick_slow()

    with session_scope() as session:
        readings = session.query(Reading).all()
        sunshines = session.query(Sunshine).all()
        actuators = session.query(ActuatorState).all()

    assert len(readings) == 4
    assert {r.zone for r in readings} == {
        "mezzanine",
        "downstairs",
        "ceiling_apex",
        "bedroom",
    }
    assert all(r.source == "ha" for r in readings)

    assert len(sunshines) == 1
    assert sunshines[0].lux == 10000.0
    assert sunshines[0].source == "ha"

    assert len(actuators) == 3
    assert all(a.source == "ha" for a in actuators)


@pytest.mark.asyncio
async def test_persistence_failure_does_not_break_push(cfg):
    """CRITICAL — guards plan-eng-review 1B.

    If repo.insert_reading_batch raises (disk full, lock contention,
    schema drift), the push dispatch path must still run. A flaky
    storage layer is not allowed to silence safety pushes.
    """
    sched = PushScheduler(ha_client=None, vapid_provider=lambda: FakeVapid())

    fake_bundle = _bundle(cfg)
    dispatch_mock = AsyncMock()

    with patch(
        "app.push.scheduler.build_full_state",
        new=AsyncMock(return_value=fake_bundle),
    ), patch(
        "app.push.scheduler.repo.insert_reading_batch",
        side_effect=RuntimeError("disk full"),
    ), patch.object(sched, "_dispatch_decisions", dispatch_mock), patch.object(
        sched, "_staleness_recovery", AsyncMock()
    ):
        await sched._tick_slow()

    assert dispatch_mock.await_count == 1, (
        "dispatch must run despite persistence error"
    )


# --- Janitor tests ---------------------------------------------------------


def test_prune_old_rows_deletes_only_pre_cutoff(cfg):
    """_prune_old_rows respects the cutoff. Newer rows survive, older die."""
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=90)

    with session_scope() as session:
        # 2 stale + 2 fresh
        repo.insert_reading_batch(
            session,
            [
                Reading(
                    ts=cutoff - timedelta(days=1),
                    zone="mezzanine",
                    temp_c=20.0,
                    humidity_pct=50.0,
                    lux_indoor=None,
                    source="ha",
                ),
                Reading(
                    ts=cutoff - timedelta(hours=1),
                    zone="bedroom",
                    temp_c=21.0,
                    humidity_pct=55.0,
                    lux_indoor=None,
                    source="ha",
                ),
                Reading(
                    ts=cutoff + timedelta(hours=1),
                    zone="mezzanine",
                    temp_c=22.0,
                    humidity_pct=50.0,
                    lux_indoor=None,
                    source="ha",
                ),
                Reading(
                    ts=now,
                    zone="bedroom",
                    temp_c=23.0,
                    humidity_pct=55.0,
                    lux_indoor=None,
                    source="ha",
                ),
            ],
        )
        session.commit()

    with session_scope() as session:
        _prune_old_rows(session, cutoff)

    with session_scope() as session:
        rows = session.query(Reading).all()
    assert len(rows) == 2
    # SQLite strips tzinfo on round-trip; compare naive-vs-naive.
    cutoff_naive = cutoff.replace(tzinfo=None)
    assert all(
        (r.ts.replace(tzinfo=None) if r.ts.tzinfo else r.ts) >= cutoff_naive
        for r in rows
    )


@pytest.mark.asyncio
async def test_janitor_runs_once_per_utc_day(cfg):
    """Two ticks in the same UTC day → janitor fires once."""
    sched = PushScheduler(ha_client=None, vapid_provider=lambda: FakeVapid())

    fake_bundle = _bundle(cfg)
    prune_calls: list[datetime] = []

    def _track_prune(session, cutoff):
        prune_calls.append(cutoff)

    with patch(
        "app.push.scheduler.build_full_state",
        new=AsyncMock(return_value=fake_bundle),
    ), patch(
        "app.push.scheduler._prune_old_rows", side_effect=_track_prune
    ), patch.object(sched, "_dispatch_decisions", AsyncMock()), patch.object(
        sched, "_staleness_recovery", AsyncMock()
    ):
        await sched._tick_slow()
        await sched._tick_slow()  # second tick same day

    assert len(prune_calls) == 1


@pytest.mark.asyncio
async def test_janitor_runs_again_on_next_utc_day(cfg):
    """When the UTC date rolls over, the janitor fires again."""
    sched = PushScheduler(ha_client=None, vapid_provider=lambda: FakeVapid())
    fake_bundle = _bundle(cfg)
    prune_calls: list[datetime] = []

    def _track_prune(session, cutoff):
        prune_calls.append(cutoff)

    # Simulate the rollover by stamping yesterday on the in-memory state.
    sched._last_prune_date = (datetime.now(tz=timezone.utc).date() - timedelta(days=1))

    with patch(
        "app.push.scheduler.build_full_state",
        new=AsyncMock(return_value=fake_bundle),
    ), patch(
        "app.push.scheduler._prune_old_rows", side_effect=_track_prune
    ), patch.object(sched, "_dispatch_decisions", AsyncMock()), patch.object(
        sched, "_staleness_recovery", AsyncMock()
    ):
        await sched._tick_slow()

    assert len(prune_calls) == 1


# --- Endpoint 404 smokes ---------------------------------------------------


def test_deleted_endpoints_not_registered():
    """Guards against accidental re-mount in main.py.

    Six endpoints disappeared in v0.6.0; if any future patch puts them
    back, this test fires before deploy. Asserted at the route-table
    level (not via HTTP) because the SPA catch-all intercepts unknown
    GETs in production.
    """
    api_paths = {
        getattr(r, "path", None) for r in app.routes
    }
    deleted = {
        "/api/readings",
        "/api/readings/latest",
        "/api/sunshine/scale",
        "/api/sunshine/latest",
        "/api/simulate",
        "/api/simulate/scenarios",
    }
    leaked = api_paths & deleted
    assert not leaked, f"deleted endpoints leaked back into routes: {leaked}"


