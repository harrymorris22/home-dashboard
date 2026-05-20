"""Calendar widget — iCloud (or any) iCal share link.

Parses the iCal feed, expands recurring rules over the next 7 days, returns
the next upcoming event + today's full list. Timezone-aware: events in any
TZ are converted to local before computing "in N minutes."

Cache: 5min in-memory. Calendar data changes rarely — refreshing more often
is wasted bandwidth.

# Request flow
#
# GET /api/widgets/calendar/next
#   ├─> ical_url empty → 503 with clear instruction
#   ├─> in-memory cache fresh (<5min)? → return cached
#   ├─> httpx GET ical_url (10s timeout)
#   │    ├─> 200 → parse with icalendar + recurring_ical_events → project → return
#   │    ├─> 4xx/5xx → 502 graceful
#   │    └─> connect / timeout → 502 graceful
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException

from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TTL = timedelta(minutes=5)

_cache: dict[str, Any] = {"fetched_at": None, "payload": None}
_lock = asyncio.Lock()


def _ensure_aware(dt_or_date: Any, default_tz: ZoneInfo) -> datetime:
    """Normalise a possibly-naive datetime or a bare date to aware datetime."""
    if isinstance(dt_or_date, datetime):
        if dt_or_date.tzinfo is None:
            return dt_or_date.replace(tzinfo=default_tz)
        return dt_or_date
    if isinstance(dt_or_date, date):
        return datetime.combine(dt_or_date, time(0, 0), tzinfo=default_tz)
    raise TypeError(f"expected date/datetime, got {type(dt_or_date)}")


def _parse_ics(ics_bytes: bytes, now: datetime, local_tz: ZoneInfo) -> dict[str, Any]:
    """Parse an iCal payload into our projected shape.

    Expands recurring events across [now, now+7d]. Returns:
      { next: {title, starts_at, location, all_day} | None, today: [...] }
    """
    from icalendar import Calendar
    import recurring_ical_events

    cal = Calendar.from_ical(ics_bytes)
    window_end = now + timedelta(days=7)
    events = recurring_ical_events.of(cal).between(now, window_end)

    projected: list[dict[str, Any]] = []
    for ev in events:
        raw_start = ev.get("DTSTART")
        if raw_start is None:
            continue
        raw = raw_start.dt
        all_day = isinstance(raw, date) and not isinstance(raw, datetime)
        starts_at = _ensure_aware(raw, local_tz)
        if starts_at < now:
            continue  # already started; skip for "next" purposes
        title = str(ev.get("SUMMARY") or "(no title)")
        location = str(ev.get("LOCATION") or "") or None
        projected.append(
            {
                "title": title,
                "starts_at": starts_at.astimezone(timezone.utc).isoformat(),
                "location": location,
                "all_day": all_day,
            }
        )

    projected.sort(key=lambda e: e["starts_at"])

    # Today's events: today in local TZ.
    local_today = now.astimezone(local_tz).date()
    today_events = [
        e for e in projected
        if datetime.fromisoformat(e["starts_at"]).astimezone(local_tz).date() == local_today
    ]

    return {
        "next": projected[0] if projected else None,
        "today": today_events,
    }


@router.get("/api/widgets/calendar/next")
async def next_event() -> dict[str, Any]:
    settings = get_settings()
    if not settings.ical_url:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ical_url_not_configured",
                "instruction": "Set ical_url in the Desk Dashboard Add-on options.",
            },
        )

    now = datetime.now(tz=timezone.utc)
    # Local TZ: just use Europe/London for this user. Could expose as a setting
    # later if the iCal feed comes from a non-local cal.
    local_tz = ZoneInfo("Europe/London")

    async with _lock:
        fetched_at = _cache["fetched_at"]
        if (
            fetched_at is not None
            and _cache["payload"] is not None
            and (now - fetched_at) < _CACHE_TTL
        ):
            return _cache["payload"]

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(settings.ical_url)
            resp.raise_for_status()
            ics_bytes = resp.content
        except httpx.HTTPError as e:
            log.warning("[calendar widget] fetch failure (%s): %s", type(e).__name__, e)
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "ical_fetch_failed",
                    "message": f"Could not fetch iCal feed: {type(e).__name__}",
                },
            ) from None

        try:
            payload = _parse_ics(ics_bytes, now, local_tz)
        except Exception as e:
            log.warning("[calendar widget] parse failure (%s): %s", type(e).__name__, e)
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "ical_parse_failed",
                    "message": f"Could not parse iCal feed: {type(e).__name__}",
                },
            ) from None

        _cache["payload"] = payload
        _cache["fetched_at"] = now
        return payload
