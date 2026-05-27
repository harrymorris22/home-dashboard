"""Coverage for the staleness contract in weather/cache.py.

Pinned after a production bug: when OWM has been failing for 14 days, the
cache used to keep returning the 14-day-old row with ``stale=True``. The
engine ignored the flag and fired the rain rule on May 13's "precip_now"
forever. Fix: enforce ``stale_after_seconds`` — beyond the threshold,
return None and let the engine degrade gracefully.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.config.loader import load_config
from app.db import repo
from app.db.models import WeatherCache
from app.db.session import session_scope
from app.weather import cache
from app.weather.schema import HourlyForecast, WeatherSnapshot


def _snap(when: datetime, *, precip_now: bool = False, conditions: str = "Clear") -> WeatherSnapshot:
    return WeatherSnapshot(
        fetched_at=when,
        temp_c=20.0,
        feels_like_c=20.0,
        humidity_pct=55.0,
        cloud_cover_pct=20.0,
        wind_speed_mps=2.0,
        wind_gust_mps=None,
        uvi=3.0,
        conditions=conditions,
        precip_now=precip_now,
        sunrise=when - timedelta(hours=4),
        sunset=when + timedelta(hours=8),
        hourly=[
            HourlyForecast(
                ts=when + timedelta(hours=h),
                temp_c=20.0,
                feels_like_c=20.0,
                humidity_pct=55.0,
                cloud_cover_pct=20.0,
                wind_speed_mps=2.0,
                uvi=3.0,
                pop=0.1,
            )
            for h in range(6)
        ],
    )


def _serialise_snap(snap: WeatherSnapshot) -> str:
    payload = asdict(snap)
    payload["fetched_at"] = snap.fetched_at.isoformat()
    payload["sunrise"] = snap.sunrise.isoformat()
    payload["sunset"] = snap.sunset.isoformat()
    payload["hourly"] = [{**asdict(h), "ts": h.ts.isoformat()} for h in snap.hourly]
    return json.dumps(payload)


def _seed_cache(when: datetime, *, precip_now: bool = False) -> WeatherSnapshot:
    """Drop a single weather_cache row stamped at ``when``."""
    snap = _snap(when, precip_now=precip_now)
    with session_scope() as session:
        repo.insert_weather(
            session, WeatherCache(fetched_at=when, payload_json=_serialise_snap(snap))
        )
        session.commit()
    return snap


async def _call_get_or_fetch():
    cfg = load_config()
    with session_scope() as session:
        return await cache.get_or_fetch(session, cfg)


async def test_fresh_cache_returns_not_stale():
    """Row younger than fetch_interval_seconds → cached + stale=False."""
    now = datetime.now(tz=timezone.utc)
    _seed_cache(now - timedelta(seconds=60))  # well within 600s default

    result = await _call_get_or_fetch()

    assert result is not None
    assert result.stale is False


async def test_owm_failure_within_stale_threshold_returns_stale_true():
    """Row > fetch_interval_seconds but < stale_after_seconds, OWM down →
    cached, stale=True. The engine still sees data but is warned."""
    now = datetime.now(tz=timezone.utc)
    # 20 min old: past fetch_interval (10 min) but inside stale_after (30 min default)
    _seed_cache(now - timedelta(minutes=20))

    with patch(
        "app.weather.cache.owm_client.fetch",
        side_effect=RuntimeError("simulated OWM 401"),
    ):
        result = await _call_get_or_fetch()

    assert result is not None
    assert result.stale is True


async def test_owm_failure_past_stale_threshold_returns_none():
    """REGRESSION: row > stale_after_seconds, OWM down → return None.

    Previously this returned a multi-day-old row with stale=True, which the
    engine ignored and used to fire the rain rule for two weeks straight.
    The fix forces None so the engine degrades to weather-offline mode.
    """
    now = datetime.now(tz=timezone.utc)
    _seed_cache(now - timedelta(days=14), precip_now=True)

    with patch(
        "app.weather.cache.owm_client.fetch",
        side_effect=RuntimeError("simulated OWM auth failure"),
    ):
        result = await _call_get_or_fetch()

    assert result is None, (
        "weather cache must return None when OWM is dead and the cached row "
        "is older than stale_after_seconds; otherwise engine fires rules on "
        "weeks-old data."
    )


async def test_cold_start_no_cache_owm_failure_returns_none():
    """No cached row, OWM fails → None (unchanged from prior behaviour)."""
    with patch(
        "app.weather.cache.owm_client.fetch",
        side_effect=RuntimeError("simulated OWM failure"),
    ):
        result = await _call_get_or_fetch()

    assert result is None


async def test_successful_refetch_writes_new_row():
    """OWM responds → new row inserted, returned with stale=False."""
    now = datetime.now(tz=timezone.utc)
    _seed_cache(now - timedelta(hours=2))  # stale

    fresh_snap = _snap(now)
    with patch(
        "app.weather.cache.owm_client.fetch",
        new=AsyncMock(return_value=fresh_snap),
    ):
        result = await _call_get_or_fetch()

    assert result is not None
    assert result.stale is False
    assert result.fetched_at == now
