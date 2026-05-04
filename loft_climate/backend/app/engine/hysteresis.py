"""Apply dwell-time / flap prevention to a fresh DashboardRecommendation.

Reads the most recent RecommendationLog entry per actuator. If the prior
entry is younger than `engine.dwell_minutes`, holds the prior value UNLESS
(a) the new urgency is "red" (safety always wins) or (b) the prior entry is
older than `stale_after_minutes`.

Pure-ish: takes the prior log records as inputs so it is testable without
the DB. The caller is responsible for fetching the prior records.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.config.schema import ConfigV1
from app.engine.types import (
    BlindGroupRecommendation,
    DashboardRecommendation,
    ZoneWindowRecommendation,
)


def _make_aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def apply_dwell(
    rec: DashboardRecommendation,
    cfg: ConfigV1,
    prior_blind: dict[str, tuple[datetime, int]],
    prior_window: dict[str, tuple[datetime, bool]],
) -> DashboardRecommendation:
    dwell = timedelta(minutes=cfg.engine.dwell_minutes)
    stale = timedelta(minutes=cfg.engine.stale_after_minutes)
    now = _make_aware(rec.ts)

    new_blinds: dict[str, BlindGroupRecommendation] = dict(rec.by_blind_group)
    for group, br in list(new_blinds.items()):
        if br.urgency == "red":
            continue
        prior = prior_blind.get(group)
        if not prior:
            continue
        prior_ts, prior_value = prior
        prior_ts = _make_aware(prior_ts)
        age = now - prior_ts
        if age >= stale:
            continue
        if age < dwell and br.blind_pct != prior_value:
            new_blinds[group] = replace(
                br,
                blind_pct=prior_value,
                scenario=f"{br.scenario}_held",
                reasons=[*br.reasons, f"Holding prior value ({prior_value}%) — dwell {dwell}."],
            )

    new_zones: dict[str, ZoneWindowRecommendation] = dict(rec.by_zone)
    for zone, zr in list(new_zones.items()):
        if zr.urgency == "red" or zr.window_open is None:
            continue
        prior = prior_window.get(zone)
        if not prior:
            continue
        prior_ts, prior_value = prior
        prior_ts = _make_aware(prior_ts)
        age = now - prior_ts
        if age >= stale:
            continue
        if age < dwell and zr.window_open != prior_value:
            new_zones[zone] = replace(
                zr,
                window_open=prior_value,
                scenario=f"{zr.scenario}_held",
                reasons=[
                    *zr.reasons,
                    f"Holding prior state ({'open' if prior_value else 'closed'}) — dwell {dwell}.",
                ],
            )

    from dataclasses import replace as _replace

    return _replace(rec, by_blind_group=new_blinds, by_zone=new_zones)
