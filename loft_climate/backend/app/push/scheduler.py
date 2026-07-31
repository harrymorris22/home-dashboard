"""Tiered async push scheduler.

Two cadences sharing the dedupe table:

  Fast tick (60 s)  — RED-only sweep. Cheap: re-runs `decide()` on whatever
                       Snapshot is current. Catches bedroom-overheat etc. in
                       <60 s without doing the full forecast pipeline.
  Slow tick (5 min) — Full snapshot via build_full_state(): OWM, sun, next
                       actions, scenario transitions, weather-offline-red
                       sustained-N counter, staleness recovery.

Each tick has its own asyncio.Lock — single-flight protection. If a tick
takes longer than its interval, the next one logs and skips.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config.loader import load_config
from app.db import repo
from app.db.models import ActuatorState, Reading, Sunshine
from app.db.session import session_scope
from app.engine.engine import decide
from app.push import repo as push_repo
from app.push.dispatcher import send_to_all
from app.push.triggers import DedupeRecord, evaluate_triggers
from app.push.types import PushPayload, TriggerDecision
from app.push.vapid import VapidKeys
from app.settings import get_settings
from app.snapshot.service import build_full_state, now_utc, snapshot_to_rows

log = logging.getLogger(__name__)


class PushScheduler:
    def __init__(
        self,
        ha_client,
        vapid_provider,  # callable returning VapidKeys | None (None when push disabled)
        fast_interval_s: int = 60,
        slow_interval_s: int = 300,
    ) -> None:
        self.ha_client = ha_client
        self.vapid_provider = vapid_provider
        self.fast_interval_s = fast_interval_s
        self.slow_interval_s = slow_interval_s
        self._fast_task: asyncio.Task[None] | None = None
        self._slow_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._fast_lock = asyncio.Lock()
        self._slow_lock = asyncio.Lock()

        # In-memory state (survives across ticks within a process):
        self._weather_offline_red_streak = 0
        self._last_global_scenario: str | None = None
        # Recovery push tracking: subscription_id → datetime when recovery push sent
        self._recovery_sent: dict[int, datetime] = {}
        # Snapshot retention: last UTC date the janitor ran. Reset on process
        # restart, which is fine — the next slow tick re-runs that day.
        # DELETE on already-pruned rows is a no-op.
        self._last_prune_date: date | None = None
        # Outdoor bias calibration: initialised from the DB on first tick so
        # we don't refit unnecessarily after a restart. None until we've
        # checked, then either a datetime (last known fit) or the epoch (no
        # calibration yet, refit ASAP).
        self._last_calibration_at: datetime | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._fast_task = asyncio.create_task(self._loop_fast(), name="push-fast")
        self._slow_task = asyncio.create_task(self._loop_slow(), name="push-slow")
        log.info("[push] scheduler started (fast=%ss, slow=%ss)", self.fast_interval_s, self.slow_interval_s)

    async def stop(self) -> None:
        self._stop.set()
        for t in (self._fast_task, self._slow_task):
            if t is not None:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    async def _sleep(self, interval_s: int) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass

    async def _loop_fast(self) -> None:
        while not self._stop.is_set():
            if self._fast_lock.locked():
                log.warning("[push] fast tick skipped — previous still running")
            else:
                async with self._fast_lock:
                    try:
                        await self._tick_fast()
                    except Exception:
                        log.exception("[push] fast tick failed")
            await self._sleep(self.fast_interval_s)

    async def _loop_slow(self) -> None:
        while not self._stop.is_set():
            if self._slow_lock.locked():
                log.warning("[push] slow tick skipped — previous still running")
            else:
                async with self._slow_lock:
                    try:
                        await self._tick_slow()
                    except Exception:
                        log.exception("[push] slow tick failed")
            await self._sleep(self.slow_interval_s)

    # --- fast tick: RED-only ------------------------------------------------

    async def _tick_fast(self) -> None:
        vapid = self.vapid_provider()
        if vapid is None:
            return  # push subsystem disabled
        # Quick path: read current zones from HA WS (already cached); no OWM call.
        with session_scope() as session:
            cfg = load_config()
            if not cfg.notifications.enabled:
                return
            bundle = await build_full_state(session, self.ha_client)  # cheapish
            if bundle.rec.global_.urgency != "red" and not any(
                b.urgency == "red" for b in bundle.rec.by_blind_group.values()
            ) and not any(
                z.urgency == "red" for z in bundle.rec.by_zone.values()
            ):
                return  # nothing red to act on
            await self._dispatch_decisions(session, bundle, vapid, slow=False)

    # --- slow tick: full pass ----------------------------------------------

    async def _tick_slow(self) -> None:
        vapid = self.vapid_provider()
        if vapid is None:
            return
        with session_scope() as session:
            cfg = load_config()
            if not cfg.notifications.enabled:
                return
            bundle = await build_full_state(session, self.ha_client)
            now_u = now_utc()

            # Snapshot persistence — wrapped in its own try/except so a
            # transient disk/lock failure can't break push dispatch
            # downstream. See plan eng-review 1B.
            try:
                rows = snapshot_to_rows(bundle, now_u)
                if rows.readings:
                    repo.insert_reading_batch(session, rows.readings)
                if rows.sunshine is not None:
                    repo.insert_sunshine(session, rows.sunshine)
                if rows.actuators:
                    repo.insert_actuator_states(session, rows.actuators)
                session.commit()
            except Exception:
                log.exception("[snapshot-persist] failed; pushes continue")
                session.rollback()

            await self._dispatch_decisions(session, bundle, vapid, slow=True)
            # Staleness recovery
            await self._staleness_recovery(session, vapid, cfg)
            # GC dedupe
            push_repo.SqliteDedupeRepo(session).gc(now_u, max_age_hours=24)

            # Daily janitor — once per UTC day, prune snapshot rows older
            # than data_retention_days. Idempotent across restarts; if
            # _last_prune_date resets to None the DELETE on already-pruned
            # rows is a no-op.
            today = now_u.date()
            if self._last_prune_date != today:
                try:
                    cutoff = now_u - timedelta(
                        days=get_settings().data_retention_days
                    )
                    _prune_old_rows(session, cutoff)
                    self._last_prune_date = today
                except Exception:
                    log.exception("[snapshot-prune] failed; non-fatal")
                    session.rollback()

            # v0.20: weekly outdoor sensor recalibration. Non-fatal on
            # failure — the last good curve keeps running. On first
            # startup this fires immediately so a fresh install starts
            # generating a curve without waiting a week.
            try:
                await self._maybe_recalibrate_outdoor(session, cfg, now_u)
            except Exception:
                log.exception("[outdoor-calibrate] failed; non-fatal")
                session.rollback()

    # --- outdoor calibration -----------------------------------------------

    async def _maybe_recalibrate_outdoor(
        self, session: Session, cfg, now_u: datetime
    ) -> None:
        """Fire the bias calibrator if enough time has passed since the
        last fit (or if none exists yet). Wired to the slow tick because
        weekly cadence doesn't need its own loop."""
        from app.outdoor.calibrator import run_calibration

        # First tick after startup: seed _last_calibration_at from DB.
        if self._last_calibration_at is None:
            latest = repo.latest_outdoor_calibration(session)
            self._last_calibration_at = latest.fitted_at if latest is not None else datetime.min.replace(tzinfo=timezone.utc)

        interval = timedelta(days=cfg.outdoor.fit_interval_days)
        if now_u - self._last_calibration_at < interval:
            return

        settings = get_settings()
        outdoor_entity = settings.ha_outdoor_entities.get("temp") if settings.ha_outdoor_entities else None
        if not outdoor_entity:
            return  # no outdoor sensor configured; nothing to calibrate
        if self.ha_client is None:
            return

        log.info(
            "[outdoor-calibrate] fitting bias curve (window=%dd, since last fit=%s)",
            cfg.outdoor.fit_window_days,
            (now_u - self._last_calibration_at),
        )
        row = await run_calibration(session, self.ha_client, cfg, outdoor_entity)
        # Record fit time regardless of persistence so we don't hammer HA
        # when there's not enough data yet.
        self._last_calibration_at = now_u
        if row is not None:
            log.info("[outdoor-calibrate] persisted new curve id=%s", row.id)

    # ---------------------------------------------------------------------

    async def _dispatch_decisions(
        self, session: Session, bundle, vapid: VapidKeys, slow: bool
    ) -> None:
        cfg = bundle.cfg
        snap = bundle.snap
        rec = bundle.rec
        next_actions = bundle.next_actions

        # Update sustained-N counter for weather=None+red.
        if snap.weather is None and rec.global_.urgency == "red":
            self._weather_offline_red_streak += 1
        else:
            self._weather_offline_red_streak = 0

        tz = ZoneInfo(cfg.location.timezone)
        now_u = now_utc()
        now_l = now_u.astimezone(tz)

        dedupe = push_repo.SqliteDedupeRepo(session)
        decisions = evaluate_triggers(
            snap=snap,
            rec=rec,
            next_actions=next_actions,
            cfg=cfg,
            dedupe=dedupe,
            now=now_u,
            now_local=now_l,
            last_global_scenario=self._last_global_scenario,
            weather_offline_red_streak=self._weather_offline_red_streak,
        )
        # Update last-seen scenario for the next tick (only on slow ticks to avoid
        # the fast loop racing).
        if slow:
            self._last_global_scenario = rec.global_.scenario

        if not decisions:
            return

        subs = push_repo.all_subscriptions(session)
        if not subs:
            return

        for d in decisions:
            await send_to_all(session, subs, d.payload, vapid)
            dedupe.record(
                DedupeRecord(
                    actuator=d.actuator,
                    scenario=d.scenario,
                    sent_at=now_u,
                    urgency=d.urgency,
                    key=d.key,
                )
            )
            log.info(
                "[push] dispatched %s (urgency=%s, devices=%d)",
                d.actuator, d.urgency, len(subs),
            )

    # ---------------------------------------------------------------------

    async def _staleness_recovery(self, session: Session, vapid, cfg) -> None:
        days = cfg.notifications.staleness_days
        stale = push_repo.stale_subscriptions(session, now_utc(), days)
        for sub in stale:
            already = self._recovery_sent.get(sub.id)
            if already and now_utc() - already < timedelta(hours=24):
                # Already nudged in the last 24h; if STILL stale at this point,
                # send the email and prune.
                self._email_nudge(cfg, sub)
                session.delete(sub)
                session.commit()
                self._recovery_sent.pop(sub.id, None)
                continue
            payload = PushPayload(
                title="Tap to keep alerts working",
                body="Your iPhone hasn't checked in for a while. Open this to reconnect.",
                tag=f"recovery:{sub.id}",
                urgency="amber",
                ts=now_utc().isoformat(),
            )
            await send_to_all(session, [sub], payload, vapid)
            self._recovery_sent[sub.id] = now_utc()

    def _email_nudge(self, cfg, sub) -> None:
        s = get_settings()
        if not s.notify_email_smtp_password:
            log.warning("[push] would email nudge for sub %s but SMTP not configured", sub.id)
            return
        recipient = s.notify_email_to or _strip_mailto(s.vapid_subject)
        if not recipient:
            return
        msg = EmailMessage()
        msg["Subject"] = "Loft Climate: notifications stopped working"
        msg["From"] = recipient
        msg["To"] = recipient
        msg.set_content(
            "Your installed PWA hasn't received a successful push in "
            f"{cfg.notifications.staleness_days}+ days. Open "
            "https://loft.harrymorris.me on the iPhone to re-enable.\n"
        )
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
                smtp.login(recipient, s.notify_email_smtp_password)
                smtp.send_message(msg)
            log.info("[push] sent staleness email to %s", recipient)
        except Exception as e:
            log.warning("[push] staleness email failed: %s", e)


def _strip_mailto(s: str) -> str:
    return s[len("mailto:") :] if s.startswith("mailto:") else s


def _prune_old_rows(session: Session, cutoff: datetime) -> None:
    """Delete snapshot rows older than `cutoff`. Logs per-table delete counts.

    Three tables share the lifecycle: ``readings`` (HA temps + humidity),
    ``sunshine`` (SW lux), ``actuator_state`` (blind positions). A 7-day
    History window means rows older than 90d (default) are dead weight.

    SQLite WAL allows concurrent reads during the DELETE so /api/history
    isn't blocked while this runs.
    """
    counts: dict[str, int] = {}
    for table_name, model in (
        ("readings", Reading),
        ("sunshine", Sunshine),
        ("actuator_state", ActuatorState),
    ):
        result = session.execute(delete(model).where(model.ts < cutoff))
        counts[table_name] = result.rowcount or 0
    session.commit()
    total = sum(counts.values())
    if total:
        log.info(
            "[snapshot-prune] removed %d rows older than %s (%s)",
            total,
            cutoff.isoformat(),
            ", ".join(f"{k}={v}" for k, v in counts.items()),
        )
