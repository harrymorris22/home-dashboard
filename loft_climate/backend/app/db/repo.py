from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActuatorState,
    Reading,
    RecommendationLog,
    Sunshine,
    WeatherCache,
)


def insert_reading_batch(session: Session, rows: Iterable[Reading]) -> list[int]:
    objs = list(rows)
    session.add_all(objs)
    session.flush()
    return [r.id for r in objs]


def latest_per_zone(session: Session) -> dict[str, Reading]:
    """Return the most recent Reading per zone."""
    out: dict[str, Reading] = {}
    # SQLite-friendly: pull all readings ordered ts desc, dedupe by zone in Python.
    # Fine for Phase 1 row counts.
    stmt = select(Reading).order_by(Reading.ts.desc())
    for r in session.scalars(stmt):
        if r.zone not in out:
            out[r.zone] = r
    return out


def readings_range(
    session: Session,
    start: datetime,
    end: datetime,
    zone: str | None = None,
) -> list[Reading]:
    stmt = select(Reading).where(Reading.ts >= start, Reading.ts <= end)
    if zone is not None:
        stmt = stmt.where(Reading.zone == zone)
    stmt = stmt.order_by(Reading.ts.asc())
    return list(session.scalars(stmt))


def insert_recommendations(session: Session, rows: Iterable[RecommendationLog]) -> None:
    session.add_all(list(rows))
    session.flush()


def latest_recommendation_for(session: Session, actuator: str) -> RecommendationLog | None:
    stmt = (
        select(RecommendationLog)
        .where(RecommendationLog.actuator == actuator)
        .order_by(RecommendationLog.ts.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def recommendations_range(
    session: Session, start: datetime, end: datetime
) -> list[RecommendationLog]:
    stmt = (
        select(RecommendationLog)
        .where(RecommendationLog.ts >= start, RecommendationLog.ts <= end)
        .order_by(RecommendationLog.ts.asc())
    )
    return list(session.scalars(stmt))


def insert_actuator_states(session: Session, rows: Iterable[ActuatorState]) -> list[int]:
    objs = list(rows)
    session.add_all(objs)
    session.flush()
    return [r.id for r in objs]


def latest_actuator_states(session: Session) -> dict[str, ActuatorState]:
    """Return the most recent ActuatorState per actuator key."""
    out: dict[str, ActuatorState] = {}
    stmt = select(ActuatorState).order_by(ActuatorState.ts.desc())
    for r in session.scalars(stmt):
        if r.actuator not in out:
            out[r.actuator] = r
    return out


def insert_sunshine(session: Session, row: Sunshine) -> int:
    session.add(row)
    session.flush()
    return row.id


def latest_sunshine(session: Session) -> Sunshine | None:
    stmt = select(Sunshine).order_by(Sunshine.ts.desc()).limit(1)
    return session.scalars(stmt).first()


def latest_weather_row(session: Session) -> WeatherCache | None:
    stmt = select(WeatherCache).order_by(WeatherCache.fetched_at.desc()).limit(1)
    return session.scalars(stmt).first()


def weather_rows_range(
    session: Session, start: datetime, end: datetime
) -> list[WeatherCache]:
    """Every cached Met.no snapshot in [start, end], oldest first.

    Used by /api/weather/history to reconstruct what Met.no said over a
    historical window (for e.g. calibrating the SwitchBot outdoor sensor
    against Met.no readings hour-by-hour).
    """
    stmt = (
        select(WeatherCache)
        .where(WeatherCache.fetched_at >= start, WeatherCache.fetched_at <= end)
        .order_by(WeatherCache.fetched_at.asc())
    )
    return list(session.scalars(stmt).all())


def insert_weather(session: Session, row: WeatherCache) -> int:
    session.add(row)
    session.flush()
    return row.id
