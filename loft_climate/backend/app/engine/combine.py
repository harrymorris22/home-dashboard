from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

from app.engine.rules import Rule
from app.engine.silence import explain_silence_blind, explain_silence_window
from app.engine.types import (
    BLIND_GROUPS,
    BlindGroupRecommendation,
    DashboardRecommendation,
    Facts,
    GlobalSummary,
    RuleOutput,
    Urgency,
    WINDOW_ZONES,
    ZoneWindowRecommendation,
)

log = logging.getLogger(__name__)

URGENCY_ORDER: dict[Urgency, int] = {"green": 0, "amber": 1, "red": 2}


def _max_urgency(values: Iterable[Urgency]) -> Urgency:
    out: Urgency = "green"
    for v in values:
        if URGENCY_ORDER[v] > URGENCY_ORDER[out]:
            out = v
    return out


def run_rules(facts: Facts, rules: list[Rule]) -> tuple[list[RuleOutput], list[str]]:
    """Run every rule with per-rule isolation. Returns (outputs, errors)."""
    outputs: list[RuleOutput] = []
    errors: list[str] = []
    for rule in rules:
        try:
            if rule.predicate(facts):
                outputs.append(rule.produce(facts))
        except Exception as e:
            log.exception("rule %s failed: %s", rule.name, e)
            errors.append(f"{rule.name}: {type(e).__name__}: {e}")
    return outputs, errors


def combine(facts: Facts, outputs: list[RuleOutput], errors: list[str]) -> DashboardRecommendation:
    # Per-actuator: highest priority wins; ties become "neutral" + amber.
    blind_winners: dict[str, list[RuleOutput]] = defaultdict(list)
    window_winners: dict[str, list[RuleOutput]] = defaultdict(list)

    blind_max_priority: dict[str, int] = {}
    window_max_priority: dict[str, int] = {}

    for o in outputs:
        for group in o.blind_targets:
            cur = blind_max_priority.get(group, -1)
            if o.priority > cur:
                blind_max_priority[group] = o.priority
                blind_winners[group] = [o]
            elif o.priority == cur:
                blind_winners[group].append(o)
        for zone in o.window_targets:
            cur = window_max_priority.get(zone, -1)
            if o.priority > cur:
                window_max_priority[zone] = o.priority
                window_winners[zone] = [o]
            elif o.priority == cur:
                window_winners[zone].append(o)

    by_blind: dict[str, BlindGroupRecommendation] = {}
    for group in BLIND_GROUPS:
        winners = blind_winners.get(group, [])
        if not winners:
            by_blind[group] = BlindGroupRecommendation(
                group=group,
                blind_pct=0,
                urgency="green",
                scenario="neutral",
                reasons=[explain_silence_blind(group, facts)],
                silence=True,
            )
            continue
        # Resolve target value.
        values = [w.blind_targets[group] for w in winners]
        if len(set(values)) == 1:
            value = values[0]
            scenario = winners[0].scenario
            urgency: Urgency = _max_urgency([w.urgency for w in winners])
            reasons = [w.reasoning for w in winners if w.reasoning]
        else:
            # Tie disagreement - default to no_change (use most-recent prior or 0).
            value = 0
            scenario = "neutral"
            urgency = "amber"
            reasons = [f"{w.rule}: {w.reasoning}" for w in winners]
        # Rules ran but produced no reasoning strings — fall back to silence.
        silence = False
        if not reasons:
            reasons = [explain_silence_blind(group, facts)]
            silence = True
        by_blind[group] = BlindGroupRecommendation(
            group=group,
            blind_pct=value,
            urgency=urgency,
            scenario=scenario,
            reasons=reasons,
            silence=silence,
        )

    by_zone: dict[str, ZoneWindowRecommendation] = {}
    for zone in WINDOW_ZONES:
        winners = window_winners.get(zone, [])
        if not winners:
            by_zone[zone] = ZoneWindowRecommendation(
                zone=zone,
                window_open=None,
                urgency="green",
                scenario="neutral",
                reasons=[explain_silence_window(zone, facts)],
                silence=True,
            )
            continue
        values = [w.window_targets[zone] for w in winners]
        if len(set(values)) == 1:
            value = values[0]
            scenario = winners[0].scenario
            urgency = _max_urgency([w.urgency for w in winners])
            reasons = [w.reasoning for w in winners if w.reasoning]
        else:
            value = None
            scenario = "neutral"
            urgency = "amber"
            reasons = [f"{w.rule}: {w.reasoning}" for w in winners]
        silence = False
        if not reasons:
            reasons = [explain_silence_window(zone, facts)]
            silence = True
        by_zone[zone] = ZoneWindowRecommendation(
            zone=zone,
            window_open=value,
            urgency=urgency,
            scenario=scenario,
            reasons=reasons,
            silence=silence,
        )

    # Global summary: highest urgency across actuators; scenario = highest-priority winning rule.
    all_urgencies = [b.urgency for b in by_blind.values()] + [z.urgency for z in by_zone.values()]
    global_urgency = _max_urgency(all_urgencies) if all_urgencies else "green"
    global_scenario = max(outputs, key=lambda o: o.priority).scenario if outputs else "comfortable"

    # Prompts: simple synthesised hints.
    prompts: list[str] = []
    if facts.weather is None:
        prompts.append("Weather offline — recommendations based on indoor sensors only.")
    if global_urgency == "red":
        prompts.append("Bedroom too hot for sleep — close door, open everything cool.")
    if facts.precip:
        prompts.append("Rain — keep windows closed even if engine wants them open.")

    return DashboardRecommendation(
        ts=facts.now,
        by_blind_group=by_blind,
        by_zone=by_zone,
        global_=GlobalSummary(scenario=global_scenario, urgency=global_urgency),
        prompts=prompts,
        rule_errors=errors,
    )
