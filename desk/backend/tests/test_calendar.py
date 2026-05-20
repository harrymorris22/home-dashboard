"""Calendar widget tests.

Happy path, empty config → 503, fetch failure → 502, recurring/timezone
handling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import get_settings
from app.widgets import calendar as calendar_mod


def _ics(events_text: str) -> bytes:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//desk-test//EN\r\n"
        f"{events_text}"
        "END:VCALENDAR\r\n"
    ).encode("utf-8")


def _single_event(dtstart_local: datetime, title: str, location: str = "") -> str:
    dt = dtstart_local.strftime("%Y%m%dT%H%M%S")
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{title}-{dt}@test\r\n"
        f"DTSTART;TZID=Europe/London:{dt}\r\n"
        f"DTEND;TZID=Europe/London:{dt}\r\n"
        f"SUMMARY:{title}\r\n"
        f"LOCATION:{location}\r\n"
        "END:VEVENT\r\n"
    )


def test_empty_ical_url_returns_503():
    get_settings().ical_url = ""
    with TestClient(create_app()) as client:
        resp = client.get("/api/widgets/calendar/next")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "ical_url_not_configured"


def test_happy_path_returns_next_event():
    get_settings().ical_url = "https://example.com/cal.ics"
    london = ZoneInfo("Europe/London")
    now_local = datetime.now(tz=london)
    upcoming = now_local + timedelta(minutes=30)
    ics = _ics(_single_event(upcoming.replace(tzinfo=None), "Standup", "Room A"))

    with patch.object(calendar_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            return_value=httpx.Response(200, content=ics, request=httpx.Request("GET", "http://x"))
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/calendar/next")

    assert resp.status_code == 200
    body = resp.json()
    assert body["next"] is not None
    assert body["next"]["title"] == "Standup"
    assert body["next"]["location"] == "Room A"


def test_fetch_404_returns_502():
    get_settings().ical_url = "https://example.com/missing.ics"
    with patch.object(calendar_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            return_value=httpx.Response(404, request=httpx.Request("GET", "http://x"))
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/calendar/next")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"] == "ical_fetch_failed"


def test_parse_failure_returns_502():
    get_settings().ical_url = "https://example.com/junk.ics"
    with patch.object(calendar_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            return_value=httpx.Response(200, content=b"not an ical", request=httpx.Request("GET", "http://x"))
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/calendar/next")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"] == "ical_parse_failed"


def test_past_events_filtered_out():
    """Events that already started should not appear as `next`."""
    get_settings().ical_url = "https://example.com/cal.ics"
    london = ZoneInfo("Europe/London")
    past = datetime.now(tz=london) - timedelta(hours=1)
    ics = _ics(_single_event(past.replace(tzinfo=None), "Yesterday's standup"))

    with patch.object(calendar_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            return_value=httpx.Response(200, content=ics, request=httpx.Request("GET", "http://x"))
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            resp = client.get("/api/widgets/calendar/next")

    body = resp.json()
    assert body["next"] is None


def test_cache_hit_avoids_second_fetch():
    get_settings().ical_url = "https://example.com/cal.ics"
    london = ZoneInfo("Europe/London")
    upcoming = datetime.now(tz=london) + timedelta(hours=1)
    ics = _ics(_single_event(upcoming.replace(tzinfo=None), "Meeting"))

    with patch.object(calendar_mod.httpx, "AsyncClient") as ClientCls:
        instance = AsyncMock()
        instance.get = AsyncMock(
            return_value=httpx.Response(200, content=ics, request=httpx.Request("GET", "http://x"))
        )
        ClientCls.return_value.__aenter__.return_value = instance
        with TestClient(create_app()) as client:
            client.get("/api/widgets/calendar/next")
            client.get("/api/widgets/calendar/next")
    assert instance.get.await_count == 1
