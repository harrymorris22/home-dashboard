from datetime import timedelta, timezone

from app.engine.engine import decide
from app.engine.hysteresis import apply_dwell
from app.simulation.scenarios import bedroom_overheat_safety, hot_sunny_breeze


def test_dwell_holds_recent_disagreement(cfg):
    snap = hot_sunny_breeze(cfg)
    rec = decide(snap)
    # Prior says blinds were UP for mezz 5 minutes ago - within dwell.
    five_min_ago = snap.now - timedelta(minutes=5)
    held = apply_dwell(
        rec,
        cfg,
        prior_blind={"mezz": (five_min_ago, 0)},
        prior_window={},
    )
    assert held.by_blind_group["mezz"].blind_pct == 0  # held to prior
    assert "Holding prior" in " ".join(held.by_blind_group["mezz"].reasons)


def test_dwell_releases_after_stale(cfg):
    snap = hot_sunny_breeze(cfg)
    rec = decide(snap)
    # 120 minutes ago, > stale_after_minutes=90 default.
    long_ago = snap.now - timedelta(minutes=120)
    held = apply_dwell(
        rec,
        cfg,
        prior_blind={"mezz": (long_ago, 0)},
        prior_window={},
    )
    assert held.by_blind_group["mezz"].blind_pct == 100  # release


def test_red_urgency_overrides_dwell(cfg):
    snap = bedroom_overheat_safety(cfg)
    rec = decide(snap)
    # Prior says bedroom blind down 1 min ago.
    held = apply_dwell(
        rec,
        cfg,
        prior_blind={"bedroom": (snap.now - timedelta(minutes=1), 100)},
        prior_window={},
    )
    # Safety wins.
    assert held.by_blind_group["bedroom"].blind_pct == 0
