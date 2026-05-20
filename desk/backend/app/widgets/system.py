"""System widget — Pi/host metrics + internet uptime aggregate.

CPU / disk / memory via psutil (cross-platform). CPU temp via Linux sysfs
thermal_zone0; gracefully returns None on non-Pi (eng-review's critical-gap
test guards this).

Uptime: aggregated from UptimeSample rows written by MonitorTask. Two
buckets — "internet" (1.1.1.1 + 8.8.8.8) and "lan" (gateway). Lets the tile
distinguish "internet down" from "LAN up but internet down."

# Request flow
#
# GET /api/widgets/system/health
#   ├─> psutil snapshot (cpu_percent, disk_usage, virtual_memory)
#   ├─> read /sys/class/thermal/thermal_zone0/temp — try/except → None
#   ├─> aggregate UptimeSamples in last 24h
#   │    ├─> per-target success rate
#   │    └─> internet vs LAN split (gateway ≠ 1.1.1.1, 8.8.8.8 → "lan")
#   └─> return {cpu_pct, cpu_temp_c, disk_pct, mem_pct, internet_24h_pct, lan_24h_pct, last_ping_ts}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psutil
from fastapi import APIRouter
from sqlalchemy import select

from app.db.models import UptimeSample
from app.db.session import session_scope

log = logging.getLogger(__name__)
router = APIRouter()

THERMAL_PATH = Path("/sys/class/thermal/thermal_zone0/temp")
PUBLIC_TARGETS = {"1.1.1.1", "8.8.8.8"}


def _read_thermal_zone() -> float | None:
    """Pi CPU temp from sysfs. Returns None on non-Pi (no file) or read error.

    Critical-gap regression guard: a test forces FileNotFoundError to assert
    we don't 500 on amd64/macOS dev boxes.
    """
    try:
        raw = THERMAL_PATH.read_text().strip()
        return int(raw) / 1000.0
    except (FileNotFoundError, PermissionError, ValueError) as e:
        log.debug("[system widget] thermal read failed (%s); cpu_temp_c=None", type(e).__name__)
        return None


def _aggregate_uptime(samples: list[UptimeSample]) -> tuple[float | None, float | None, datetime | None]:
    """Split samples into internet (public targets) vs LAN (everything else)
    and compute success rate over the window. Returns (internet_pct, lan_pct,
    last_ts). Either pct may be None if no samples exist in that bucket yet.
    """
    if not samples:
        return None, None, None

    internet = [s for s in samples if s.target in PUBLIC_TARGETS]
    lan = [s for s in samples if s.target not in PUBLIC_TARGETS]

    def _rate(rows: list[UptimeSample]) -> float | None:
        if not rows:
            return None
        ok = sum(1 for r in rows if r.success)
        return (ok / len(rows)) * 100

    last_ts = max(s.ts for s in samples)
    return _rate(internet), _rate(lan), last_ts


@router.get("/api/widgets/system/health")
async def health() -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=24)

    cpu_pct = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_temp_c = _read_thermal_zone()

    with session_scope() as session:
        # Comparison vs naive value: SQLite strips tz, so compare ts as naive
        # against window_start.replace(tzinfo=None).
        cutoff = window_start.replace(tzinfo=None)
        samples = list(
            session.scalars(
                select(UptimeSample).where(UptimeSample.ts >= cutoff)
            )
        )
    internet_pct, lan_pct, last_ts = _aggregate_uptime(samples)

    return {
        "cpu_pct": cpu_pct,
        "cpu_temp_c": cpu_temp_c,
        "disk_pct": disk.percent,
        "mem_pct": mem.percent,
        "internet_24h_pct": internet_pct,
        "lan_24h_pct": lan_pct,
        "last_ping_ts": last_ts.replace(tzinfo=timezone.utc).isoformat() if last_ts else None,
    }
