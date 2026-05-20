"""Stock widget — yfinance (Yahoo Finance scraper) with SQLite stale-cache.

Happy path: yfinance.Ticker.history → projected price + 7d sparkline. TTL is
60s during LSE market hours (08:00–16:30 UK), 1h outside.

Failure path (eng-review 1B): on any yfinance exception, serve the last
successful payload from StockCache and set `stale: true`. The frontend
shows a small "stale" badge. Yahoo periodically shape-shifts its internal
API — this is the load-bearing fallback that keeps the tile honest rather
than empty.

# Request flow
#
# GET /api/widgets/stock/{ticker}
#   ├─> in-memory TTL cache hit? → return cached
#   ├─> yfinance.Ticker(ticker).history(period='7d', interval='1h')
#   │    ├─> ok → project, persist to StockCache, update memory cache, return
#   │    └─> exception → load latest StockCache row → return with stale=true
#   └─> empty result AND no StockCache row → 404 (unknown ticker)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.models import StockCache
from app.db.session import session_scope

log = logging.getLogger(__name__)
router = APIRouter()

# In-memory TTL cache keyed by ticker.
_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
_lock = asyncio.Lock()

LONDON = ZoneInfo("Europe/London")
LSE_OPEN = dtime(8, 0)
LSE_CLOSE = dtime(16, 30)


def _market_hours_ttl(now: datetime) -> timedelta:
    """60s during LSE market hours, 1h outside.

    Market closes on weekends; treat sat/sun as off-hours.
    """
    local = now.astimezone(LONDON)
    if local.weekday() >= 5:
        return timedelta(hours=1)
    if LSE_OPEN <= local.time() <= LSE_CLOSE:
        return timedelta(seconds=60)
    return timedelta(hours=1)


def _fetch_yfinance_sync(ticker: str) -> dict[str, Any]:
    """Run in a thread — yfinance is sync-only. Returns projected dict.

    Raises if Yahoo returns empty data (unknown ticker) or any internal error.
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    hist = t.history(period="7d", interval="1h")
    if hist.empty:
        raise ValueError(f"yfinance returned empty history for {ticker}")

    closes = hist["Close"].dropna()
    if closes.empty:
        raise ValueError(f"yfinance returned no close prices for {ticker}")

    price = float(closes.iloc[-1])
    # Day change: compare last close vs first close of latest trading day.
    # 1h interval × ~7h trading day ≈ 7 points; safer to compare vs 1d ago.
    if len(closes) >= 2:
        day_start = float(closes.iloc[max(0, len(closes) - 8)])
        day_change_abs = price - day_start
        day_change_pct = (day_change_abs / day_start) * 100 if day_start else 0.0
    else:
        day_change_abs = 0.0
        day_change_pct = 0.0

    # Sparkline: down-sample to ~24 evenly spaced points for the tile.
    n = len(closes)
    step = max(1, n // 24)
    sparkline = [float(closes.iloc[i]) for i in range(0, n, step)][-24:]

    currency = t.info.get("currency", "GBP") if hasattr(t, "info") else "GBP"

    return {
        "ticker": ticker,
        "price": price,
        "currency": currency,
        "day_change_abs": day_change_abs,
        "day_change_pct": day_change_pct,
        "sparkline": sparkline,
    }


async def _persist_to_cache(ticker: str, payload: dict[str, Any], when: datetime) -> None:
    def _upsert():
        with session_scope() as session:
            row = session.get(StockCache, ticker)
            if row is None:
                row = StockCache(
                    ticker=ticker,
                    fetched_at=when,
                    payload_json=json.dumps(payload),
                )
                session.add(row)
            else:
                row.fetched_at = when
                row.payload_json = json.dumps(payload)

    await asyncio.to_thread(_upsert)


async def _load_from_cache(ticker: str) -> tuple[datetime, dict[str, Any]] | None:
    def _load():
        with session_scope() as session:
            row = session.scalars(
                select(StockCache).where(StockCache.ticker == ticker)
            ).first()
            if row is None:
                return None
            return row.fetched_at, json.loads(row.payload_json)

    return await asyncio.to_thread(_load)


@router.get("/api/widgets/stock/{ticker}")
async def stock(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper()
    now = datetime.now(tz=timezone.utc)

    async with _lock:
        cached = _cache.get(ticker)
        if cached is not None:
            fetched_at, payload = cached
            ttl = _market_hours_ttl(fetched_at)
            if (now - fetched_at) < ttl:
                return {**payload, "stale": False, "last_success_at": fetched_at.isoformat()}

        try:
            payload = await asyncio.to_thread(_fetch_yfinance_sync, ticker)
        except Exception as e:
            log.warning("[stock widget] yfinance failure for %s (%s): %s", ticker, type(e).__name__, e)
            persisted = await _load_from_cache(ticker)
            if persisted is None:
                # Never been successfully fetched — likely a typo / unknown ticker.
                raise HTTPException(
                    status_code=404,
                    detail={"error": "ticker_unknown_or_unreachable", "ticker": ticker},
                ) from None
            fetched_at, payload = persisted
            return {**payload, "stale": True, "last_success_at": fetched_at.isoformat()}

        # Happy path: update both caches.
        _cache[ticker] = (now, payload)
        await _persist_to_cache(ticker, payload, now)
        return {**payload, "stale": False, "last_success_at": now.isoformat()}
