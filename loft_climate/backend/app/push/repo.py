"""Tiny repo for PushSubscription + PushDedupeEntry rows."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PushDedupeEntry, PushSubscription
from app.push.triggers import DedupeRecord, DedupeRepo
from app.push.types import Urgency


def all_subscriptions(session: Session) -> list[PushSubscription]:
    return list(session.scalars(select(PushSubscription).order_by(PushSubscription.id)))


def find_by_endpoint(session: Session, endpoint: str) -> PushSubscription | None:
    stmt = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    return session.scalars(stmt).first()


def upsert(session: Session, row: PushSubscription) -> PushSubscription:
    existing = find_by_endpoint(session, row.endpoint)
    if existing is not None:
        existing.p256dh = row.p256dh
        existing.auth = row.auth
        existing.ua = row.ua
        existing.label = row.label
        session.commit()
        return existing
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def delete_by_endpoint(session: Session, endpoint: str) -> bool:
    sub = find_by_endpoint(session, endpoint)
    if sub is None:
        return False
    session.delete(sub)
    session.commit()
    return True


def stale_subscriptions(
    session: Session, now: datetime, days: int
) -> list[PushSubscription]:
    threshold = now - timedelta(days=days)
    out: list[PushSubscription] = []
    for s in all_subscriptions(session):
        if s.last_success_at is None:
            # Never succeeded; only count as stale if the row itself is older
            # than threshold (avoids alarming on a fresh subscription that
            # hasn't been pushed to yet).
            if s.created_at and (s.created_at.replace(tzinfo=timezone.utc) if s.created_at.tzinfo is None else s.created_at) < threshold:
                out.append(s)
            continue
        last = s.last_success_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < threshold:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Dedupe repo (SQLite-backed, implements DedupeRepo Protocol)
# ---------------------------------------------------------------------------


class SqliteDedupeRepo(DedupeRepo):
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_for(self, actuator: str, scenario: str) -> DedupeRecord | None:
        stmt = (
            select(PushDedupeEntry)
            .where(
                PushDedupeEntry.actuator == actuator,
                PushDedupeEntry.scenario == scenario,
            )
            .order_by(PushDedupeEntry.sent_at.desc())
            .limit(1)
        )
        row = self.session.scalars(stmt).first()
        if row is None:
            return None
        sent_at = row.sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        return DedupeRecord(
            actuator=row.actuator,
            scenario=row.scenario,
            sent_at=sent_at,
            urgency=row.urgency,  # type: ignore[arg-type]
            key=row.key,
        )

    def has_key(self, key: str) -> bool:
        stmt = select(PushDedupeEntry.id).where(PushDedupeEntry.key == key).limit(1)
        return self.session.scalar(stmt) is not None

    def record(self, rec: DedupeRecord) -> None:
        self.session.add(
            PushDedupeEntry(
                key=rec.key,
                actuator=rec.actuator,
                scenario=rec.scenario,
                sent_at=rec.sent_at,
                urgency=rec.urgency,
            )
        )
        self.session.commit()

    def gc(self, now: datetime, max_age_hours: int = 24) -> int:
        threshold = now - timedelta(hours=max_age_hours)
        rows = list(
            self.session.scalars(
                select(PushDedupeEntry).where(PushDedupeEntry.sent_at < threshold)
            )
        )
        for r in rows:
            self.session.delete(r)
        if rows:
            self.session.commit()
        return len(rows)
