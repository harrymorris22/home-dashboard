"""Stock widget tests.

Happy path, market-hours TTL, yfinance failure → SQLite stale-cache fallback
(eng-review 1B regression guard), unknown ticker → 404."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.db.models import StockCache
from app.db.session import session_scope
from app.main import create_app
from app.widgets import stock as stock_mod


HAPPY_PAYLOAD = {
    "ticker": "LQQ3.L",
    "price": 12.45,
    "currency": "GBP",
    "day_change_abs": 0.30,
    "day_change_pct": 2.47,
    "sparkline": [12.0, 12.1, 12.2, 12.3, 12.4, 12.45],
}


def test_happy_path_returns_projected_shape():
    with patch.object(stock_mod, "_fetch_yfinance_sync", return_value=HAPPY_PAYLOAD):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/stock/LQQ3.L")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "LQQ3.L"
    assert body["price"] == 12.45
    assert body["currency"] == "GBP"
    assert body["stale"] is False
    assert len(body["sparkline"]) == 6


def test_cache_hit_does_not_recall_yfinance():
    with patch.object(stock_mod, "_fetch_yfinance_sync", return_value=HAPPY_PAYLOAD) as mock_fetch:
        with TestClient(create_app()) as client:
            client.get("/api/widgets/stock/LQQ3.L")
            client.get("/api/widgets/stock/LQQ3.L")
    assert mock_fetch.call_count == 1


def test_market_hours_ttl_60s():
    london_open = datetime(2026, 5, 20, 9, 0, tzinfo=ZoneInfo("Europe/London")).astimezone(timezone.utc)
    assert stock_mod._market_hours_ttl(london_open) == timedelta(seconds=60)


def test_off_hours_ttl_one_hour():
    london_midnight = datetime(2026, 5, 20, 23, 0, tzinfo=ZoneInfo("Europe/London")).astimezone(timezone.utc)
    assert stock_mod._market_hours_ttl(london_midnight) == timedelta(hours=1)


def test_weekend_ttl_one_hour():
    saturday_noon = datetime(2026, 5, 23, 12, 0, tzinfo=ZoneInfo("Europe/London")).astimezone(timezone.utc)
    assert stock_mod._market_hours_ttl(saturday_noon) == timedelta(hours=1)


def test_yfinance_failure_serves_stale_cache():
    """CRITICAL — eng-review 1B regression guard.

    When yfinance throws (Yahoo API shape-shift, network error), the previously
    persisted StockCache row must be served with stale=true.
    """
    # Prime the cache with a successful fetch.
    with patch.object(stock_mod, "_fetch_yfinance_sync", return_value=HAPPY_PAYLOAD):
        with TestClient(create_app()) as client:
            primer = client.get("/api/widgets/stock/LQQ3.L")
            assert primer.status_code == 200
            assert primer.json()["stale"] is False

    # Confirm SQLite has the row.
    with session_scope() as session:
        row = session.get(StockCache, "LQQ3.L")
        assert row is not None
        assert json.loads(row.payload_json)["price"] == 12.45

    # Wipe in-memory cache to force a fresh yfinance call.
    stock_mod._cache.clear()

    # Now make yfinance fail.
    with patch.object(stock_mod, "_fetch_yfinance_sync", side_effect=RuntimeError("yahoo shape changed")):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/stock/LQQ3.L")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert body["price"] == 12.45  # from cache
    assert body["last_success_at"] is not None


def test_unknown_ticker_returns_404():
    with patch.object(stock_mod, "_fetch_yfinance_sync", side_effect=ValueError("empty data")):
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/stock/UNKNOWNXYZ")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "ticker_unknown_or_unreachable"
