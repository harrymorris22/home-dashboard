from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    zone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    lux_indoor: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    __table_args__ = (Index("ix_readings_ts_zone", "ts", "zone"),)


class RecommendationLog(Base):
    __tablename__ = "recommendation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    actuator: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "blind:mezz" or "window:bedroom"
    value: Mapped[str] = mapped_column(String(64), nullable=False)  # "open"/"closed"/"100"/"0"...
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)  # green/amber/red
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")


class WeatherCache(Base):
    __tablename__ = "weather_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


# Feedback model removed in v0.6.0 — table left on disk because the project
# uses Base.metadata.create_all (no Alembic). Re-introduce the model if a
# feedback feature returns; the table is still there.


class ActuatorState(Base):
    """Current physical state of a blind or window.

    `actuator` keys are stable strings: ``blind:mezz``, ``blind:downstairs``,
    ``blind:bedroom``, ``window:mezzanine``, ``window:downstairs``,
    ``window:ceiling_apex``, ``window:bedroom``.

    Phase 1: written by the manual entry form.
    Phase 2: written by Home Assistant cover/state changes.
    """

    __tablename__ = "actuator_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    actuator: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(32), nullable=False)  # "100" or "open"/"closed"
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")


class Sunshine(Base):
    """Single SW-glazing light reading.

    Phase 1: written by manual entry (a 0–5 sunshine scale mapped to a lux value).
    Phase 2: written by the Aqara Light Sensor T1 mounted inside the SW window.
    """

    __tablename__ = "sunshine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    lux: Mapped[float] = mapped_column(Float, nullable=False)
    scale: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0–5 if from manual scale
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")


class PushSubscription(Base):
    """Web Push subscription. One row per device that opted in.

    `endpoint` is the unique APNs URL provided by the browser. `p256dh` + `auth`
    are the per-subscription encryption keys; we use them via pywebpush. ZHA can
    push us → invalid → 410 Gone → row deleted by dispatcher.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    ua: Mapped[str | None] = mapped_column(String(256), nullable=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PushDedupeEntry(Base):
    """Short-lived dedupe / cooldown record for push triggers.

    `key` shape: ``<source>:<actuator>:<scenario>:<YYYY-MM-DDTHH>``.
    GC older than 24 h on each scheduler tick.
    """

    __tablename__ = "push_dedupe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(192), index=True, nullable=False)
    actuator: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
