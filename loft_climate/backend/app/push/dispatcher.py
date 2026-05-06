"""pywebpush wrapper. Sends one or many encrypted pushes via APNs (for Safari
PWA endpoints) or FCM (for Android / Chrome). Auto-prunes 410-Gone subscriptions
and tracks per-subscription failure counters.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable

from cryptography.hazmat.primitives import serialization
from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.db.models import PushSubscription
from app.push.types import PushPayload, SendResult, Urgency
from app.push.vapid import VapidKeys

log = logging.getLogger(__name__)


_URGENCY_HEADER: dict[Urgency, str] = {
    "red": "high",
    "amber": "normal",
    "green": "low",  # green never produces a trigger; defensive default
}
_URGENCY_TTL: dict[Urgency, int] = {
    "red": 600,
    "amber": 1800,
    "green": 3600,
}

_PAYLOAD_CEILING_BYTES = 3 * 1024  # leave headroom under iOS ~4 KB


def _pem_to_raw_b64url(pem: str) -> str:
    """py_vapid's from_string PEM detection is fragile across versions.
    Converting our stored PEM to the raw 32-byte base64url form takes the
    `from_raw` code path, which has been stable since py_vapid 1.x.
    """
    private_key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    raw = private_key.private_numbers().private_value.to_bytes(32, "big")  # type: ignore[attr-defined]
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _serialise_payload(p: PushPayload) -> str:
    body = json.dumps(asdict(p), separators=(",", ":"))
    if len(body.encode("utf-8")) > _PAYLOAD_CEILING_BYTES:
        # Truncate the body field to keep the rest of the payload intact.
        keep = _PAYLOAD_CEILING_BYTES // 2
        truncated = PushPayload(
            v=p.v,
            title=p.title[:80],
            body=p.body[:keep] + "…",
            tag=p.tag,
            url=p.url,
            urgency=p.urgency,
            ts=p.ts,
        )
        body = json.dumps(asdict(truncated), separators=(",", ":"))
    return body


def _classify(exc: WebPushException) -> tuple[str, int | None, str]:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    text = getattr(getattr(exc, "response", None), "text", "") or str(exc)
    if status in (404, 410):
        return "gone", status, text
    if status == 429 or status == 503:
        return "rate_limited", status, text
    return "error", status, text


def _send_one_sync(
    sub: PushSubscription, payload_body: str, vapid: VapidKeys, urgency: Urgency
) -> SendResult:
    """Sync (runs in a worker thread). Maps pywebpush response → SendResult."""
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=payload_body,
            vapid_private_key=_pem_to_raw_b64url(vapid.private_pem),
            vapid_claims={"sub": vapid.subject},
            ttl=_URGENCY_TTL[urgency],
            headers={"Urgency": _URGENCY_HEADER[urgency]},
        )
        return SendResult(
            subscription_id=sub.id,
            status="ok",
            http_status=201,
            detail=None,
            sent_at=datetime.now(tz=timezone.utc),
        )
    except WebPushException as e:
        kind, status, detail = _classify(e)
        return SendResult(
            subscription_id=sub.id,
            status=kind,  # type: ignore[arg-type]
            http_status=status,
            detail=detail,
            sent_at=datetime.now(tz=timezone.utc),
        )


async def send_to_subscription(
    session: Session,
    sub: PushSubscription,
    payload: PushPayload,
    vapid: VapidKeys,
) -> SendResult:
    body = _serialise_payload(payload)
    result = await asyncio.to_thread(_send_one_sync, sub, body, vapid, payload.urgency)

    if result.status == "ok":
        sub.last_success_at = result.sent_at
        sub.failure_count = 0
        session.commit()
    elif result.status == "gone":
        log.info("[push] subscription %s returned gone; pruning", sub.id)
        session.delete(sub)
        session.commit()
    elif result.status == "rate_limited":
        log.warning("[push] sub %s rate-limited (%s)", sub.id, result.http_status)
        sub.last_error_at = result.sent_at
        session.commit()
    else:
        sub.last_error_at = result.sent_at
        sub.failure_count = (sub.failure_count or 0) + 1
        if sub.failure_count >= 5:
            log.warning("[push] sub %s exceeded failure threshold; pruning", sub.id)
            session.delete(sub)
        session.commit()
    return result


async def send_to_all(
    session: Session,
    subscriptions: Iterable[PushSubscription],
    payload: PushPayload,
    vapid: VapidKeys,
) -> list[SendResult]:
    """Fan out to every subscription. Bounded fan-out is a TODO (T-PUSH-1)."""
    results: list[SendResult] = []
    for sub in subscriptions:
        results.append(await send_to_subscription(session, sub, payload, vapid))
    return results
