from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.history.service import history_range

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history")
def get_history(
    start: datetime | None = None,
    end: datetime | None = None,
    zones: str | None = Query(default=None, description="Comma-separated zone ids"),
    target_points: int = Query(default=200, ge=10, le=2000),
    session: Session = Depends(get_session),
):
    end = end or datetime.now(tz=timezone.utc)
    start = start or end - timedelta(days=7)
    zones_list = [z.strip() for z in zones.split(",")] if zones else None
    return history_range(session, start, end, zones_list, target_points=target_points)
