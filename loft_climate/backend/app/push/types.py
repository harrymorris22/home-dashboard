"""Push types — kept separate so triggers.py and dispatcher.py share without
importing each other."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Urgency = Literal["green", "amber", "red"]


@dataclass(frozen=True)
class PushPayload:
    """JSON-serialised body of a push. Carries `v: 1` for forward-compat."""

    title: str
    body: str
    tag: str
    url: str = "/"
    urgency: Urgency = "amber"
    ts: str = ""
    v: int = 1


@dataclass(frozen=True)
class TriggerDecision:
    """One push that *should* be sent. The scheduler hands a list of these to
    the dispatcher."""

    key: str  # dedupe / hour-bucket key
    actuator: str
    scenario: str
    urgency: Urgency
    payload: PushPayload
    bypass_quiet_hours: bool
    bypass_snooze: bool = False  # only `recovery` pushes set this


@dataclass(frozen=True)
class SendResult:
    subscription_id: int
    status: Literal["ok", "gone", "rate_limited", "error"]
    http_status: int | None
    detail: str | None
    sent_at: datetime
