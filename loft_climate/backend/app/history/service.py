from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from app.db import repo


def _downsample(rows: list[dict], target_points: int) -> list[dict]:
    if len(rows) <= target_points:
        return rows
    step = len(rows) // target_points
    return rows[::step]


def history_range(
    session: Session,
    start: datetime,
    end: datetime,
    zones: Iterable[str] | None = None,
    target_points: int = 200,
) -> dict:
    zones_list = list(zones) if zones else None
    points: list[dict] = []
    if zones_list:
        for z in zones_list:
            for r in repo.readings_range(session, start, end, zone=z):
                points.append(_reading_to_dict(r))
    else:
        for r in repo.readings_range(session, start, end):
            points.append(_reading_to_dict(r))
    points.sort(key=lambda p: (p["ts"], p["zone"]))

    # Group by zone for downsample.
    by_zone: dict[str, list[dict]] = {}
    for p in points:
        by_zone.setdefault(p["zone"], []).append(p)
    downsampled: list[dict] = []
    for zone_pts in by_zone.values():
        downsampled.extend(_downsample(zone_pts, target_points))

    recs = []
    for r in repo.recommendations_range(session, start, end):
        recs.append(
            {
                "ts": r.ts.isoformat(),
                "actuator": r.actuator,
                "value": r.value,
                "urgency": r.urgency,
                "scenario": r.scenario,
                "reasoning": r.reasoning,
            }
        )
    return {"points": downsampled, "recommendations": recs}


def _reading_to_dict(r) -> dict:
    return {
        "ts": r.ts.isoformat(),
        "zone": r.zone,
        "temp_c": r.temp_c,
        "humidity_pct": r.humidity_pct,
        "lux_indoor": r.lux_indoor,
    }
