from datetime import timedelta

from app.engine.forecast import project_actions
from tests.scenarios import hot_sunny_breeze, post_sunset_purge


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


# --- v0.13: past hourly-entry filtering ------------------------------------


def test_past_hourly_entries_are_skipped(cfg):
    """REGRESSION: Met.no's hourly forecast starts at the top of the current
    hour. If we're 40 min into the 11:00 hour, hourly[0].ts is 11:00 UTC —
    already 40 min past. Without this filter, project_actions emitted
    transitions with past timestamps that rendered as "now" in the UI AND
    leaked stale Met.no forecast values into reasoning that contradicted
    the live outdoor-sensor override in base_snap.weather.temp_c.
    """
    from dataclasses import replace

    snap = hot_sunny_breeze(cfg)
    # Move "now" 40 min past hourly[0].ts so it counts as past.
    past_now = snap.weather.hourly[0].ts + timedelta(minutes=40)
    stale_snap = replace(snap, now=past_now)

    out = project_actions(stale_snap, horizon_hours=12)
    assert all(t["ts"] > snap.weather.hourly[0].ts.isoformat() for t in out), (
        "project_actions must not emit transitions at or before base_snap.now"
    )


def test_first_transition_is_strictly_in_the_future(cfg):
    """Every returned transition has ts > base_snap.now, no exceptions.

    Complements the previous test: iterates the whole return list rather
    than just checking hourly[0] was filtered. Guards against a fix that
    happens to skip only h=0 but not h=1 if hourly[1] is also past.
    """
    from dataclasses import replace

    snap = hot_sunny_breeze(cfg)
    past_now = snap.weather.hourly[0].ts + timedelta(minutes=1)  # 1 min into current hour
    stale_snap = replace(snap, now=past_now)

    out = project_actions(stale_snap, horizon_hours=12)
    for t in out:
        assert t["ts"] > past_now.isoformat(), (
            f"transition at ts={t['ts']!r} is not strictly after "
            f"base_snap.now={past_now.isoformat()!r}"
        )
