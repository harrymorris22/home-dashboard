"""Coverage for HAClient.history_period URL construction (v0.20.2).

REGRESSION: an earlier version sent ``start.isoformat()`` unencoded,
which included ``+00:00`` in the query string. HA's URL parser
decodes ``+`` as space per WHATWG rules, corrupting the timestamp
and returning 400 Bad Request. Fix: normalise to ``Z``-suffixed UTC
and URL-encode the path segment.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.sensors.homeassistant import HAClient


@pytest.mark.asyncio
async def test_history_period_url_has_no_plus_signs():
    """The composed URL must never contain a raw + in a timestamp — that's
    the actual bug shape we're pinning here."""
    client = HAClient("http://ha.test:8123", "fake-token")
    start = datetime(2026, 7, 3, 0, 13, 50, 496346, tzinfo=timezone.utc)
    end = datetime(2026, 8, 2, 0, 13, 50, 496346, tzinfo=timezone.utc)

    captured_url = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_url["url"] = str(request.url)
        return httpx.Response(200, json=[[]])

    with respx.mock:
        respx.get(url__startswith="http://ha.test:8123/api/history/period/").mock(
            side_effect=_handler
        )
        await client.history_period(
            "sensor.indoor_outdoor_meter_6d73_temperature", start, end
        )

    url = captured_url["url"]
    # No raw + in a timestamp position — either Z-suffixed or %2B-encoded.
    assert "+00:00" not in url, f"raw +00:00 in URL: {url!r}"
    # Contains the Z-suffix somewhere (either in the path or in the encoded query)
    assert "Z" in url
    # Path segment has the encoded start timestamp (colons percent-encoded)
    assert "2026-07-03T00%3A13%3A50Z" in url
    # end_time query param survives the trip
    assert "end_time=2026-08-02T00%3A13%3A50Z" in url
    # Entity id present as filter
    assert "filter_entity_id=sensor.indoor_outdoor_meter_6d73_temperature" in url


@pytest.mark.asyncio
async def test_history_period_filters_non_numeric_states():
    """`unavailable`, `unknown`, blank, non-parseable states are skipped."""
    client = HAClient("http://ha.test:8123", "tok")
    start = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc)

    fake_series = [
        [
            {"state": "22.5", "last_changed": "2026-07-01T10:00:00+00:00"},
            {"state": "unavailable", "last_changed": "2026-07-01T10:05:00+00:00"},
            {"state": "unknown", "last_changed": "2026-07-01T10:10:00+00:00"},
            {"state": "", "last_changed": "2026-07-01T10:15:00+00:00"},
            {"state": "abc", "last_changed": "2026-07-01T10:20:00+00:00"},
            {"state": "23.1", "last_changed": "2026-07-01T10:30:00+00:00"},
        ]
    ]

    with respx.mock:
        respx.get(url__startswith="http://ha.test:8123/api/history/period/").mock(
            return_value=httpx.Response(200, json=fake_series)
        )
        result = await client.history_period("sensor.x", start, end)

    values = [v for _, v in result]
    assert values == [22.5, 23.1]


@pytest.mark.asyncio
async def test_history_period_empty_series_returns_empty_list():
    client = HAClient("http://ha.test:8123", "tok")
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 2, tzinfo=timezone.utc)

    with respx.mock:
        respx.get(url__startswith="http://ha.test:8123/api/history/period/").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await client.history_period("sensor.x", start, end)

    assert result == []


@pytest.mark.asyncio
async def test_history_period_handles_naive_datetime_as_utc():
    """Callers may pass naive datetimes; must not crash, must send Z."""
    client = HAClient("http://ha.test:8123", "tok")
    start = datetime(2026, 7, 1, 0, 0)  # naive
    end = datetime(2026, 7, 2, 0, 0)    # naive

    captured = {}

    def _handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[[]])

    with respx.mock:
        respx.get(url__startswith="http://ha.test:8123/api/history/period/").mock(
            side_effect=_handler
        )
        await client.history_period("sensor.x", start, end)

    assert "2026-07-01T00%3A00%3A00Z" in captured["url"]
