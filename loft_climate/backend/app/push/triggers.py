"""Trigger evaluation — pure logic, no I/O.

Given the current snapshot + recommendation + next_actions, plus dedupe
state and the user's notifications config, return a list of TriggerDecision
objects the dispatcher should fire.

Filter order, applied per candidate:
  1. Snooze (suppresses all but recovery)
  2. Cooldown — by `(actuator, scenario)`, regardless of hour bucket
  3. Hour-bucket dedupe
  4. Quiet hours (RED can bypass per `red_bypass_quiet_hours`)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable

from app.config.schema import ConfigV1, Notifications
from app.engine.types import DashboardRecommendation, Snapshot
from app.push.types import PushPayload, TriggerDecision, Urgency

# ---------------------------------------------------------------------------
# Dedupe / cooldown adapter (lets tests inject in-memory state)
# ---------------------------------------------------------------------------


@dataclass
class DedupeRecord:
    actuator: str
    scenario: str
    sent_at: datetime
    urgency: Urgency
    key: str


class DedupeRepo:
    """Protocol-ish; tests pass an in-memory variant."""

    def latest_for(self, actuator: str, scenario: str) -> DedupeRecord | None:
        raise NotImplementedError

    def has_key(self, key: str) -> bool:
        raise NotImplementedError

    def record(self, rec: DedupeRecord) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hh(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H")


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _in_quiet_hours(now_local: datetime, start: str, end: str) -> bool:
    s = _parse_hhmm(start)
    e = _parse_hhmm(end)
    cur = now_local.time()
    if s <= e:
        return s <= cur < e
    # Wraps midnight (e.g. 23:00–07:00).
    return cur >= s or cur < e


def _is_snoozed(notif: Notifications, now: datetime) -> bool:
    if notif.snooze_until is None:
        return False
    snooze = notif.snooze_until
    if snooze.tzinfo is None and now.tzinfo is not None:
        from datetime import timezone as _tz
        snooze = snooze.replace(tzinfo=_tz.utc)
    return now < snooze


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


def _candidate_red_actuators(
    snap: Snapshot, rec: DashboardRecommendation, hh: str
) -> list[TriggerDecision]:
    out: list[TriggerDecision] = []
    cur_blinds = dict(snap.current_blind)
    cur_windows = dict(snap.current_window)

    for group, blind in rec.by_blind_group.items():
        if blind.urgency != "red" or blind.scenario == "neutral":
            continue
        # Only push if current physical state disagrees.
        cur = cur_blinds.get(group)
        if cur is not None:
            same = (blind.blind_pct >= 75 and cur >= 75) or (
                blind.blind_pct <= 25 and cur <= 25
            )
            if same:
                continue
        actuator = f"blind:{group}"
        out.append(
            TriggerDecision(
                key=f"red:{actuator}:{blind.scenario}:{hh}",
                actuator=actuator,
                scenario=blind.scenario,
                urgency="red",
                payload=PushPayload(
                    title=f"Heat warning — {group}",
                    body=blind.reasons[0] if blind.reasons else "Bedroom too hot for sleep.",
                    tag=f"red:{actuator}:{blind.scenario}:{hh}",
                    urgency="red",
                    ts=snap.now.isoformat(),
                ),
                bypass_quiet_hours=True,
            )
        )

    for zone, window in rec.by_zone.items():
        if window.urgency != "red" or window.window_open is None:
            continue
        cur = cur_windows.get(zone)
        if cur is not None and cur == window.window_open:
            continue
        actuator = f"window:{zone}"
        verb = "Open" if window.window_open else "Close"
        out.append(
            TriggerDecision(
                key=f"red:{actuator}:{window.scenario}:{hh}",
                actuator=actuator,
                scenario=window.scenario,
                urgency="red",
                payload=PushPayload(
                    title=f"{verb} {zone} window now",
                    body=window.reasons[0] if window.reasons else "Bedroom safety override.",
                    tag=f"red:{actuator}:{window.scenario}:{hh}",
                    urgency="red",
                    ts=snap.now.isoformat(),
                ),
                bypass_quiet_hours=True,
            )
        )
    return out


def _candidate_imminent_actions(
    snap: Snapshot,
    next_actions: list[dict],
    hh: str,
    now: datetime,
    transition_window_minutes: int,
) -> list[TriggerDecision]:
    out: list[TriggerDecision] = []
    horizon = now + timedelta(minutes=transition_window_minutes)
    for a in next_actions:
        urgency = a.get("urgency", "amber")
        if urgency == "green":
            continue
        try:
            ts = datetime.fromisoformat(a["ts"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if ts > horizon:
            continue
        if ts < now - timedelta(minutes=2):
            continue  # already past
        actuator = a["actuator"]
        scenario = a.get("scenario", "")
        target = a.get("to")
        title_verb = (
            "Close" if (str(actuator).startswith("blind:") and isinstance(target, int) and target >= 75)
            else "Open" if (str(actuator).startswith("blind:") and isinstance(target, int) and target <= 25)
            else "Open" if target == "open"
            else "Close" if target == "closed"
            else "Adjust"
        )
        out.append(
            TriggerDecision(
                key=f"txn:{actuator}:{scenario}:{hh}",
                actuator=actuator,
                scenario=scenario,
                urgency=urgency,  # type: ignore[arg-type]
                payload=PushPayload(
                    title=f"{title_verb} {actuator.replace(':', ' ').strip()}",
                    body=a.get("reasoning") or "Coming up in <15 min.",
                    tag=f"txn:{actuator}:{scenario}:{hh}",
                    urgency=urgency,  # type: ignore[arg-type]
                    ts=snap.now.isoformat(),
                ),
                bypass_quiet_hours=urgency == "red",
            )
        )
    return out


def _candidate_scenario_transition(
    snap: Snapshot,
    rec: DashboardRecommendation,
    last_global_scenario: str | None,
    hh: str,
) -> TriggerDecision | None:
    cur = rec.global_.scenario
    cur_urg = rec.global_.urgency
    if cur in ("comfortable", "neutral"):
        return None
    if last_global_scenario == cur:
        return None
    if cur_urg == "green":
        return None
    actuator = "global"
    return TriggerDecision(
        key=f"scenario:{actuator}:{cur}:{hh}",
        actuator=actuator,
        scenario=cur,
        urgency=cur_urg,
        payload=PushPayload(
            title=f"{cur.replace('_', ' ').title()}",
            body="Engine has changed scenario. Open the dashboard.",
            tag=f"scenario:{actuator}:{cur}:{hh}",
            urgency=cur_urg,
            ts=snap.now.isoformat(),
        ),
        bypass_quiet_hours=cur_urg == "red",
    )


def _candidate_weather_offline_red(
    snap: Snapshot,
    rec: DashboardRecommendation,
    weather_offline_red_streak: int,
    sustained_threshold: int,
    hh: str,
) -> TriggerDecision | None:
    if snap.weather is not None:
        return None
    if rec.global_.urgency != "red":
        return None
    if weather_offline_red_streak < sustained_threshold:
        return None
    return TriggerDecision(
        key=f"weather_offline_red:{hh}",
        actuator="global",
        scenario="weather_offline_red",
        urgency="red",
        payload=PushPayload(
            title="Indoor red — weather offline",
            body="Engine flagged red on indoor sensors alone. Check the dashboard.",
            tag=f"weather_offline_red:{hh}",
            urgency="red",
            ts=snap.now.isoformat(),
        ),
        bypass_quiet_hours=True,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def evaluate_triggers(
    snap: Snapshot,
    rec: DashboardRecommendation,
    next_actions: list[dict],
    cfg: ConfigV1,
    dedupe: DedupeRepo,
    now: datetime,
    now_local: datetime,
    last_global_scenario: str | None,
    weather_offline_red_streak: int,
) -> list[TriggerDecision]:
    notif = cfg.notifications
    if not notif.enabled:
        return []

    hh = _hh(now)
    candidates: list[TriggerDecision] = []
    candidates.extend(_candidate_red_actuators(snap, rec, hh))
    candidates.extend(
        _candidate_imminent_actions(
            snap, next_actions, hh, now, notif.transition_window_minutes
        )
    )
    sc = _candidate_scenario_transition(snap, rec, last_global_scenario, hh)
    if sc is not None:
        candidates.append(sc)
    wo = _candidate_weather_offline_red(
        snap, rec, weather_offline_red_streak, notif.sustained_weather_offline_ticks, hh
    )
    if wo is not None:
        candidates.append(wo)

    snoozed = _is_snoozed(notif, now)
    in_quiet = _in_quiet_hours(now_local, notif.quiet_hours_start, notif.quiet_hours_end)
    cooldown = timedelta(minutes=notif.cooldown_minutes)

    out: list[TriggerDecision] = []
    for cand in candidates:
        # 1. Snooze. Even red is suppressed when the user explicitly muted.
        if snoozed and not cand.bypass_snooze:
            continue
        # 2. Cooldown by (actuator, scenario), regardless of hour bucket.
        prev = dedupe.latest_for(cand.actuator, cand.scenario)
        if prev is not None and now - prev.sent_at < cooldown:
            continue
        # 3. Hour-bucket dedupe.
        if dedupe.has_key(cand.key):
            continue
        # 4. Quiet hours.
        if in_quiet and cand.urgency != "red":
            continue
        if in_quiet and cand.urgency == "red" and not (
            notif.red_bypass_quiet_hours or cand.bypass_quiet_hours
        ):
            continue

        out.append(cand)
    return out
