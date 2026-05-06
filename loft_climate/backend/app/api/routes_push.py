"""Push subscription / test / vapid_public endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.loader import load_config, save_config
from app.db.models import PushSubscription
from app.db.session import get_session
from app.push import repo as push_repo
from app.push.dispatcher import send_to_all
from app.push.types import PushPayload
from app.push.vapid import VapidKeys, force_regenerate, load_or_create
from app.settings import get_settings

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribePayload(BaseModel):
    endpoint: str
    keys: SubscriptionKeys
    ua: str | None = None
    label: str | None = None


class UnsubscribePayload(BaseModel):
    endpoint: str


class SnoozePayload(BaseModel):
    until: datetime | None = None  # null clears snooze


def _vapid_or_503(request: Request) -> VapidKeys:
    keys = getattr(request.app.state, "vapid_keys", None)
    if keys is None:
        raise HTTPException(
            status_code=503,
            detail="Push subsystem unavailable. Check /notifications for diagnostics.",
        )
    return keys


@router.get("/vapid_public")
def vapid_public(request: Request):
    keys = _vapid_or_503(request)
    return {"public_key": keys.public_b64url, "subject": keys.subject}


@router.post("/vapid/regenerate", status_code=201)
def vapid_regenerate(request: Request):
    """Manual recovery: replace the keypair after a corruption-detect halt or
    when the user wants to force re-subscribe across all devices."""
    s = get_settings()
    keys = force_regenerate(s.vapid_keys_path, s.vapid_subject)
    request.app.state.vapid_keys = keys
    return {"public_key": keys.public_b64url}


@router.get("/status")
def push_status(request: Request, session: Session = Depends(get_session)):
    keys = getattr(request.app.state, "vapid_keys", None)
    cfg = load_config()
    return {
        "enabled": cfg.notifications.enabled,
        "vapid_ready": keys is not None,
        "vapid_subject": getattr(keys, "subject", None),
        "subscription_count": len(push_repo.all_subscriptions(session)),
        "snooze_until": cfg.notifications.snooze_until.isoformat()
        if cfg.notifications.snooze_until
        else None,
    }


@router.post("/subscribe", status_code=201)
def subscribe(
    payload: SubscribePayload,
    session: Session = Depends(get_session),
):
    sub = PushSubscription(
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        ua=payload.ua,
        label=payload.label,
        created_at=datetime.now(tz=timezone.utc),
    )
    saved = push_repo.upsert(session, sub)
    return {"id": saved.id}


@router.delete("/subscribe", status_code=204)
def unsubscribe(
    payload: UnsubscribePayload,
    session: Session = Depends(get_session),
):
    push_repo.delete_by_endpoint(session, payload.endpoint)
    return None


@router.get("/subscriptions")
def list_subscriptions(session: Session = Depends(get_session)):
    out = []
    for s in push_repo.all_subscriptions(session):
        out.append(
            {
                "id": s.id,
                "ua": s.ua,
                "label": s.label,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
                "last_error_at": s.last_error_at.isoformat() if s.last_error_at else None,
                "failure_count": s.failure_count,
            }
        )
    return {"items": out}


@router.post("/test")
async def send_test(request: Request, session: Session = Depends(get_session)):
    keys = _vapid_or_503(request)
    subs = push_repo.all_subscriptions(session)
    if not subs:
        raise HTTPException(status_code=404, detail="No subscriptions registered")
    payload = PushPayload(
        title="Loft Climate test",
        body="Push delivery is working. This is a test notification.",
        tag="test",
        urgency="amber",
        ts=datetime.now(tz=timezone.utc).isoformat(),
    )
    results = await send_to_all(session, subs, payload, keys)
    return {
        "results": [
            {
                "subscription_id": r.subscription_id,
                "status": r.status,
                "http_status": r.http_status,
            }
            for r in results
        ]
    }


@router.post("/snooze")
def snooze(payload: SnoozePayload):
    cfg = load_config()
    cfg.notifications.snooze_until = payload.until
    save_config(cfg)
    return {
        "snooze_until": cfg.notifications.snooze_until.isoformat()
        if cfg.notifications.snooze_until
        else None
    }
