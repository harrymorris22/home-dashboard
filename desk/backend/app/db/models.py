"""ORM models for the desk dashboard.

Two tables, both write-heavy and time-bound:
  - UptimeSample: one row per (timestamp, target) from the MonitorTask
  - StockCache: one row per ticker, overwritten on each successful yfinance hit
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UptimeSample(Base):
    """Per-target ping result. Rotation across 1.1.1.1, 8.8.8.8, gateway.

    Read path: aggregated to "internet 95% / LAN 100%" by the system widget.
    Write path: appended by MonitorTask every 30s. Pruned to last 7d.
    """

    __tablename__ = "uptime_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    target: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_uptime_ts_target", "ts", "target"),)


class StockCache(Base):
    """Last successful response per ticker — the stale-cache fallback for the
    stock widget when yfinance throws (eng-review 1B).

    Single row per ticker; ON CONFLICT replaces the row. Read path: served
    verbatim with stale=true when the live yfinance call fails. Write path:
    overwritten after every successful fetch.
    """

    __tablename__ = "stock_cache"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
