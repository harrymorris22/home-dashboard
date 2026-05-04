from datetime import timedelta

from app.engine.forecast import project_actions
from app.simulation.scenarios import hot_sunny_breeze, post_sunset_purge


def test_no_weather_returns_empty(cfg):
    snap = hot_sunny_breeze(cfg)
    from dataclasses import replace
    assert project_actions(replace(snap, weather=None)) == []


def test_returns_list_of_transitions(cfg):
    snap = hot_sunny_breeze(cfg)
    out = project_actions(snap, horizon_hours=12)
    assert isinstance(out, list)
    # Each transition shape
    for t in out:
        assert "ts" in t
        assert "actuator" in t
        assert "to" in t


def test_transitions_are_ordered_by_time(cfg):
    snap = hot_sunny_breeze(cfg)
    out = project_actions(snap, horizon_hours=12)
    timestamps = [t["ts"] for t in out]
    assert timestamps == sorted(timestamps)


def test_horizon_caps_results(cfg):
    snap = hot_sunny_breeze(cfg)
    capped = project_actions(snap, horizon_hours=12, max_transitions=2)
    assert len(capped) <= 2
