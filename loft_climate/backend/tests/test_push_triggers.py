"""Pure-logic tests for evaluate_triggers — no I/O, in-memory dedupe repo."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config.loader import load_config
from app.engine.engine import decide
from app.push.triggers import DedupeRecord, DedupeRepo, evaluate_triggers
from tests.scenarios import (
    bedroom_overheat_safety,
    hot_sunny_breeze,
    mild_outdoor_warm_indoor,
)


class InMemoryDedupe(DedupeRepo):
    def __init__(self) -> None:
        self._records: list[DedupeRecord] = []

    def latest_for(self, actuator: str, scenario: str) -> DedupeRecord | None:
        candidates = [r for r in self._records if r.actuator == actuator and r.scenario == scenario]
        return max(candidates, key=lambda r: r.sent_at) if candidates else None

    def has_key(self, key: str) -> bool:
        return any(r.key == key for r in self._records)

    def record(self, rec: DedupeRecord) -> None:
        self._records.append(rec)


def _evaluate(snap, *, dedupe=None, last_scenario=None, weather_streak=0, now_utc=None):
    cfg = snap.config
    if now_utc is None:
        now_utc = snap.now if snap.now.tzinfo else snap.now.replace(tzinfo=timezone.utc)
    tz = ZoneInfo(cfg.location.timezone)
    return evaluate_triggers(
        snap=snap,
        rec=decide(snap),
        next_actions=[],
        cfg=cfg,
        dedupe=dedupe or InMemoryDedupe(),
        now=now_utc,
        now_local=now_utc.astimezone(tz),
        last_global_scenario=last_scenario,
        weather_offline_red_streak=weather_streak,
    )


def test_red_overheat_fires_with_bypass(cfg):
    snap = bedroom_overheat_safety(cfg)
    decisions = _evaluate(snap)
    assert decisions, "expected at least one decision"
    assert any(d.urgency == "red" and d.bypass_quiet_hours for d in decisions)


def test_quiet_hours_suppress_amber(cfg):
    snap = mild_outdoor_warm_indoor(cfg)
    # Force quiet-hours window over the scenario's local 'now'.
    cfg2 = snap.config.model_copy(update={
        "notifications": snap.config.notifications.model_copy(update={
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "23:59",
        })
    })
    snap2 = replace(snap, config=cfg2)
    decisions = _evaluate(snap2)
    # No amber should leak through.
    assert all(d.urgency == "red" for d in decisions)


def test_cooldown_blocks_within_window(cfg):
    snap = bedroom_overheat_safety(cfg)
    dedupe = InMemoryDedupe()
    decisions_a = _evaluate(snap, dedupe=dedupe)
    assert decisions_a
    # Record the first decision as if dispatcher had sent it.
    dedupe.record(DedupeRecord(
        actuator=decisions_a[0].actuator,
        scenario=decisions_a[0].scenario,
        sent_at=snap.now if snap.now.tzinfo else snap.now.replace(tzinfo=timezone.utc),
        urgency=decisions_a[0].urgency,
        key=decisions_a[0].key,
    ))
    # Re-evaluate within the 30-min cooldown.
    decisions_b = _evaluate(snap, dedupe=dedupe)
    assert all(d.actuator != decisions_a[0].actuator for d in decisions_b), \
        "cooldown should suppress same actuator+scenario"


def test_cooldown_first_then_bucket(cfg):
    """Boundary case: red at 14:59 + re-evaluation at 15:01 (different hour
    bucket, same actuator+scenario) — cooldown still suppresses."""
    snap = bedroom_overheat_safety(cfg)
    dedupe = InMemoryDedupe()
    base_now = datetime(2026, 5, 6, 14, 59, tzinfo=timezone.utc)
    decisions_a = _evaluate(snap, dedupe=dedupe, now_utc=base_now)
    assert decisions_a
    dedupe.record(DedupeRecord(
        actuator=decisions_a[0].actuator,
        scenario=decisions_a[0].scenario,
        sent_at=base_now,
        urgency=decisions_a[0].urgency,
        key=decisions_a[0].key,
    ))
    later = base_now + timedelta(minutes=2)  # 15:01 — new hour bucket
    decisions_b = _evaluate(snap, dedupe=dedupe, now_utc=later)
    assert all(d.actuator != decisions_a[0].actuator for d in decisions_b)


def test_weather_offline_red_needs_sustained_streak(cfg):
    snap = mild_outdoor_warm_indoor(cfg)
    snap_no_weather = replace(snap, weather=None)
    # Streak below threshold → no weather_offline_red decision.
    decisions = _evaluate(snap_no_weather, weather_streak=1)
    assert all(d.scenario != "weather_offline_red" for d in decisions)


def test_disabled_returns_empty(cfg):
    snap = bedroom_overheat_safety(cfg)
    cfg2 = snap.config.model_copy(update={
        "notifications": snap.config.notifications.model_copy(update={"enabled": False})
    })
    snap2 = replace(snap, config=cfg2)
    decisions = _evaluate(snap2)
    assert decisions == []


def test_snooze_suppresses_all(cfg):
    snap = bedroom_overheat_safety(cfg)
    far_future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    cfg2 = snap.config.model_copy(update={
        "notifications": snap.config.notifications.model_copy(update={
            "snooze_until": far_future,
        })
    })
    snap2 = replace(snap, config=cfg2)
    decisions = _evaluate(snap2)
    assert decisions == []
