"""Supervised internet/LAN uptime probe.

Rotates pings across N targets (default: 1.1.1.1, 8.8.8.8, router gateway).
Inserts one UptimeSample per target per tick into SQLite. The system widget
later aggregates 24h success rate from those samples.

# MonitorTask lifecycle
#
# start()
#   └─> _loop (asyncio.Task)
#         ├─> _tick()           [every 30s]
#         │    ├─> ping target_1 ─┐
#         │    ├─> ping target_2 ─┼─> gather + insert UptimeSample x N
#         │    └─> ping target_N ─┘
#         │    └─> [once per UTC day] GC samples older than retention
#         │
#         └─> exception path: log + sleep 5s + continue
#                             (NEVER dies silently — eng-review 4A)
#
# stop() signals _stop.set(); _loop exits on next sleep wake.

The supervisor pattern is load-bearing: a single uncaught exception (DNS
flake, OS reporting unreachable differently across kernels, asyncio cancel
mid-write) would otherwise kill the task and the uptime tile would silently
stay at "last good aggregate forever." The outer `while not stop.is_set()`
+ try/except per-tick mirrors loft_climate's PushScheduler resilience.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete

from app.db.models import UptimeSample
from app.db.session import session_scope

log = logging.getLogger(__name__)


async def _ping_once(host: str, port: int = 53, timeout_s: float = 2.0) -> tuple[bool, float | None]:
    """Best-effort reachability check via TCP open to a well-known port.

    We don't shell out to `ping` (ICMP) because:
      - Many container envs deny raw sockets for unprivileged processes
      - TCP-on-53 (DNS) is open on 1.1.1.1, 8.8.8.8, and most consumer routers
      - asyncio.open_connection is non-blocking, no subprocess overhead

    Returns (success, latency_ms or None).
    """
    start = time.perf_counter()
    try:
        # open_connection returns (reader, writer); we close immediately.
        fut = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(fut, timeout=timeout_s)
        latency_ms = (time.perf_counter() - start) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, latency_ms
    except (OSError, asyncio.TimeoutError):
        return False, None


def _discover_gateway() -> str | None:
    """Best-effort default-gateway discovery for Linux containers.

    Reads /proc/net/route. Returns the LAN gateway IP, or None if it
    can't figure it out (non-Linux dev box, exotic networking).
    """
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.split()
                # Default route has Destination 0.0.0.0
                if fields[1] == "00000000" and int(fields[3], 16) & 2:
                    gw_hex = fields[2]
                    # /proc/net/route stores IPs little-endian hex
                    octets = [int(gw_hex[i : i + 2], 16) for i in (6, 4, 2, 0)]
                    return ".".join(str(o) for o in octets)
    except (FileNotFoundError, PermissionError, ValueError, IndexError):
        return None
    return None


class MonitorTask:
    def __init__(
        self,
        targets: list[str],
        interval_s: int = 30,
        retention_days: int = 7,
    ) -> None:
        self.targets = list(targets)
        self.interval_s = interval_s
        self.retention_days = retention_days
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_prune_date: date | None = None

    async def start(self) -> None:
        # One-shot gateway discovery on startup; appended if found.
        gw = _discover_gateway()
        if gw and gw not in self.targets:
            self.targets.append(gw)
            log.info("[monitor] gateway %s appended to ping targets", gw)
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="desk-monitor")
        log.info("[monitor] started (interval=%ss, targets=%s)", self.interval_s, self.targets)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        # Supervisor: any uncaught exception → log + sleep 5s + retry.
        # NEVER dies silently. Guards eng-review 4A.
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                log.exception("[monitor] tick crashed; retrying in 5s")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=5)
                    return  # stop signal arrived during recovery sleep
                except asyncio.TimeoutError:
                    continue
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
                return
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        now = datetime.now(tz=timezone.utc)
        # Ping all targets in parallel; treat each result independently.
        results = await asyncio.gather(
            *(_ping_once(t) for t in self.targets), return_exceptions=True
        )
        rows: list[UptimeSample] = []
        for target, result in zip(self.targets, results):
            if isinstance(result, BaseException):
                success, latency = False, None
            else:
                success, latency = result
            rows.append(
                UptimeSample(ts=now, target=target, success=success, latency_ms=latency)
            )
        with session_scope() as session:
            session.add_all(rows)

        # Janitor: prune once per UTC day. Idempotent across restarts; a missed
        # day just runs on next slow tick. DELETE on empty range is a no-op.
        today = now.date()
        if self._last_prune_date != today:
            cutoff = now - timedelta(days=self.retention_days)
            with session_scope() as session:
                result = session.execute(
                    delete(UptimeSample).where(UptimeSample.ts < cutoff)
                )
                deleted = result.rowcount or 0
            if deleted:
                log.info("[monitor] pruned %d samples older than %dd", deleted, self.retention_days)
            self._last_prune_date = today
