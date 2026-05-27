"""Coverage for snapshot/service.py::snapshot_to_rows.

Pure function: takes a StateBundle + a `now` timestamp, returns
SnapshotRows ready for insert. The whole point is that the v0.6 slow
tick can persist HA-sourced state to the History tables without going
through any HTTP path.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.engine.types import (
    BlindGroupRecommendation,
    DashboardRecommendation,
    GlobalSummary,
    Snapshot,
    ZoneWindowRecommendation,
)
from app.sensors.source import ZoneSensorReading
from app.snapshot.service import (
    SNAPSHOT_SOURCE,
    SnapshotRows,
    StateBundle,
    snapshot_to_rows,
)


# --- Builders --------------------------------------------------------------


def _zone_reading(zone: str, temp: float = 22.5, hum: float = 55.0) -> ZoneSensorReading:
    return ZoneSensorReading(
        zone=zone,
        ts=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        temp_c=temp,
        humidity_pct=hum,
        lux_indoor=None,
    )


def _make_bundle(cfg, *, zones=None, sw_lux=None, blinds=None, ha_known_blinds=None):
    """Assemble a minimal StateBundle for the function under test.

    The function only touches `bundle.snap.zones`, `bundle.snap.sw_lux`,
    `bundle.snap.current_blind`, and `bundle.ha_known_blinds`, so we stub
    everything else.

    Default ``ha_known_blinds`` is the full set of groups in ``blinds`` — i.e.
    HA reported every group. Pass an empty frozenset to simulate
    "HA returned nothing, values came from manual fallback".
    """
    if zones is None:
        zones = {
            "mezzanine": _zone_reading("mezzanine", 23.0, 50.0),
            "downstairs": _zone_reading("downstairs", 21.5, 55.0),
            "ceiling_apex": _zone_reading("ceiling_apex", 25.0, 45.0),
            "bedroom": _zone_reading("bedroom", 22.0, 60.0),
        }
    if blinds is None:
        blinds = {"mezz": 50, "downstairs": 25, "bedroom": 100}
    if ha_known_blinds is None:
        ha_known_blinds = frozenset(blinds.keys())

    snap = Snapshot(
        now=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        zones=zones,
        weather=None,
        sun=_dummy_sun(),
        config=cfg,
        sw_lux=sw_lux,
        current_blind=blinds,
        current_window={},
    )
    rec = DashboardRecommendation(
        ts=snap.now,
        by_blind_group={},
        by_zone={},
        global_=GlobalSummary(scenario="test", urgency="green"),
        prompts=[],
        rule_errors=[],
    )
    return StateBundle(
        cfg=cfg,
        snap=snap,
        rec=rec,
        next_actions=[],
        ha_known_blinds=ha_known_blinds,
    )


def _dummy_sun():
    from app.sun.calculator import SunPosition

    return SunPosition(
        elevation_deg=30.0,
        azimuth_deg=180.0,
        sunrise=datetime(2026, 5, 6, 5, 0, tzinfo=timezone.utc),
        sunset=datetime(2026, 5, 6, 20, 0, tzinfo=timezone.utc),
        is_daylight=True,
    )


# --- Tests -----------------------------------------------------------------


def test_happy_path_full_bundle(cfg):
    """4 zones + sunshine + 3 blinds → 4 readings, 1 sunshine, 3 actuators."""
    now = datetime(2026, 5, 6, 12, 30, tzinfo=timezone.utc)
    bundle = _make_bundle(cfg, sw_lux=12000.0)

    rows = snapshot_to_rows(bundle, now)

    assert isinstance(rows, SnapshotRows)
    assert len(rows.readings) == 4
    assert {r.zone for r in rows.readings} == {
        "mezzanine",
        "downstairs",
        "ceiling_apex",
        "bedroom",
    }
    assert all(r.ts == now for r in rows.readings)

    assert rows.sunshine is not None
    assert rows.sunshine.lux == 12000.0
    assert rows.sunshine.scale is None
    assert rows.sunshine.ts == now

    assert len(rows.actuators) == 3
    assert {a.actuator for a in rows.actuators} == {
        "blind:mezz",
        "blind:downstairs",
        "blind:bedroom",
    }
    assert {a.value for a in rows.actuators} == {"50", "25", "100"}


def test_skips_zone_with_none_reading(cfg):
    """A zone whose HA entity returned nothing must not produce a row.

    The snapshot builder simply omits absent zones — we never see a
    None-valued ZoneSensorReading — so this also covers the no-entry
    case. Verify an explicit None survives without raising.
    """
    now = datetime.now(tz=timezone.utc)
    zones = {
        "mezzanine": _zone_reading("mezzanine"),
        "downstairs": _zone_reading("downstairs"),
        "bedroom": _zone_reading("bedroom"),
        # ceiling_apex absent
    }
    bundle = _make_bundle(cfg, zones=zones)
    rows = snapshot_to_rows(bundle, now)

    assert len(rows.readings) == 3
    assert "ceiling_apex" not in {r.zone for r in rows.readings}


def test_no_sunshine_when_sw_lux_is_none(cfg):
    bundle = _make_bundle(cfg, sw_lux=None)
    rows = snapshot_to_rows(bundle, datetime.now(tz=timezone.utc))

    assert rows.sunshine is None
    # readings + actuators unaffected
    assert len(rows.readings) == 4
    assert len(rows.actuators) == 3


def test_no_actuators_when_blinds_empty(cfg):
    bundle = _make_bundle(cfg, blinds={})
    rows = snapshot_to_rows(bundle, datetime.now(tz=timezone.utc))

    assert rows.actuators == []
    # readings + sunshine unaffected
    assert len(rows.readings) == 4


def test_source_field_stamped_on_every_row(cfg):
    """Every emitted row must carry source="ha", regardless of what was
    historically in the DB. This is the load-bearing label that lets
    /api/history queries treat HA-sourced and manual-sourced rows
    interchangeably while operators can still distinguish them.
    """
    now = datetime.now(tz=timezone.utc)
    bundle = _make_bundle(cfg, sw_lux=8000.0)
    rows = snapshot_to_rows(bundle, now)

    assert SNAPSHOT_SOURCE == "ha"
    assert all(r.source == "ha" for r in rows.readings)
    assert rows.sunshine is not None and rows.sunshine.source == "ha"
    assert all(a.source == "ha" for a in rows.actuators)


def test_actuator_rows_only_persist_ha_known_groups(cfg):
    """REGRESSION (v0.9.0): when current_blind values came from the
    DbCachedActuatorStateSource fallback (e.g., user POSTed via
    /api/blinds/state because Tahoma never reports), the slow-tick
    snapshot must NOT re-stamp them with source="ha". Doing so would
    pollute the audit trail — a manual entry would appear in history as
    if HA reported it.

    The fix: snapshot_to_rows checks bundle.ha_known_blinds and only
    emits rows for groups that actually came from HA.
    """
    now = datetime.now(tz=timezone.utc)
    # mezz came from HA, downstairs + bedroom from manual fallback.
    bundle = _make_bundle(
        cfg,
        blinds={"mezz": 50, "downstairs": 100, "bedroom": 0},
        ha_known_blinds=frozenset({"mezz"}),
    )
    rows = snapshot_to_rows(bundle, now)

    actuators_by_key = {a.actuator: a for a in rows.actuators}
    assert "blind:mezz" in actuators_by_key
    assert "blind:downstairs" not in actuators_by_key, (
        "downstairs came from manual fallback; the slow tick must not "
        "re-stamp it with source='ha'."
    )
    assert "blind:bedroom" not in actuators_by_key


def test_actuator_rows_empty_when_ha_returns_nothing(cfg):
    """When HA cover source is dead entirely (every group came from
    manual fallback), snapshot writes ZERO actuator rows — the DB
    already has the canonical source='manual' rows from /api/blinds/state.
    """
    now = datetime.now(tz=timezone.utc)
    bundle = _make_bundle(
        cfg,
        blinds={"mezz": 0, "downstairs": 100, "bedroom": 50},
        ha_known_blinds=frozenset(),
    )
    rows = snapshot_to_rows(bundle, now)
    assert rows.actuators == []
