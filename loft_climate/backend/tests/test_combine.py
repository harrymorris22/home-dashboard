from datetime import datetime, timezone

from app.engine.classifier import build_facts
from app.engine.combine import combine, run_rules
from app.engine.rules import Rule
from app.engine.types import RuleOutput
from app.simulation.scenarios import hot_sunny_breeze


def _facts(cfg):
    snap = hot_sunny_breeze(cfg)
    return build_facts(snap.now, snap.zones, snap.weather, snap.sun, snap.config)


def test_priority_wins(cfg):
    f = _facts(cfg)
    low = Rule("low", 70, lambda _f: True, lambda _f: RuleOutput("low", 70, blind_targets={"mezz": 0}, urgency="green", scenario="low"))
    high = Rule("high", 90, lambda _f: True, lambda _f: RuleOutput("high", 90, blind_targets={"mezz": 100}, urgency="red", scenario="high"))
    outs, errs = run_rules(f, [low, high])
    rec = combine(f, outs, errs)
    assert rec.by_blind_group["mezz"].blind_pct == 100
    assert rec.by_blind_group["mezz"].urgency == "red"


def test_tie_disagreement_neutral(cfg):
    f = _facts(cfg)
    a = Rule("a", 80, lambda _f: True, lambda _f: RuleOutput("a", 80, blind_targets={"mezz": 0}, scenario="a"))
    b = Rule("b", 80, lambda _f: True, lambda _f: RuleOutput("b", 80, blind_targets={"mezz": 100}, scenario="b"))
    outs, errs = run_rules(f, [a, b])
    rec = combine(f, outs, errs)
    assert rec.by_blind_group["mezz"].scenario == "neutral"
    assert rec.by_blind_group["mezz"].urgency == "amber"


def test_independent_actuator_namespaces(cfg):
    """A blind rule and a window rule both fire; both are reflected."""
    f = _facts(cfg)
    blind_rule = Rule("blinds", 80, lambda _f: True, lambda _f: RuleOutput("blinds", 80, blind_targets={"mezz": 100}, scenario="solar"))
    window_rule = Rule("windows", 80, lambda _f: True, lambda _f: RuleOutput("windows", 80, window_targets={"mezzanine": True}, scenario="cross"))
    outs, errs = run_rules(f, [blind_rule, window_rule])
    rec = combine(f, outs, errs)
    assert rec.by_blind_group["mezz"].blind_pct == 100
    assert rec.by_zone["mezzanine"].window_open is True


def test_run_rules_isolates_exceptions(cfg):
    f = _facts(cfg)
    def bad_pred(_):
        raise ValueError("nope")
    bad = Rule("bad", 50, bad_pred, lambda _f: RuleOutput("bad", 50))
    outs, errs = run_rules(f, [bad])
    assert outs == []
    assert errs and "bad" in errs[0]
