"""Pure decision engine entrypoint."""
from __future__ import annotations

from app.engine.classifier import build_facts
from app.engine.combine import combine, run_rules
from app.engine.rules import ALL_RULES, Rule
from app.engine.types import DashboardRecommendation, Snapshot


def decide(snap: Snapshot, rules: list[Rule] | None = None) -> DashboardRecommendation:
    """Pure: same Snapshot input → same recommendation output."""
    rules = rules if rules is not None else ALL_RULES
    facts = build_facts(
        now=snap.now,
        zones=snap.zones,
        weather=snap.weather,
        sun=snap.sun,
        cfg=snap.config,
        sw_lux=snap.sw_lux,
        current_blind=snap.current_blind,
    )
    outputs, errors = run_rules(facts, rules)
    return combine(facts, outputs, errors)
