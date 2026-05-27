"""User-asserted blind state.

Why this exists: Tahoma's open/close-only blinds (no position sensor) accept
commands but never report state back to HA. cover.* entities sit at
``state: unknown`` forever, our HA cover source skips them, and the dashboard
loses the "currently up/down" annotation. v0.9.0 fills that gap by letting the
user mark blind state from the UI. Writes go to ``actuator_state`` with
``source="manual"``; the existing DbCachedActuatorStateSource picks them up
on the next snapshot, and CompositeActuatorStateSource's HA-first ordering
means a real HA position (if it ever returns) still wins.

Endpoints
---------
- ``POST /api/blinds/state``   — set one or more blind groups in one call
- ``GET  /api/blinds/state``   — read the current latest-per-group view

Group ids: ``mezz``, ``downstairs``, ``bedroom`` (matches engine BLIND_GROUPS).
Position semantics: ``0`` = fully up (out of window), ``100`` = fully down
(covering window). For binary blinds, send 0 or 100. The dashboard's ALL-UP
and ALL-DOWN bulk buttons send 0 and 100 respectively for every group.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, RootModel
from sqlalchemy.orm import Session

from app.db import repo
from app.db.models import ActuatorState
from app.db.session import session_scope
from app.engine.types import BLIND_GROUPS

router = APIRouter(prefix="/api/blinds", tags=["blinds"])


class BlindStateBody(RootModel[dict[str, int]]):
    """A partial dict of {group: position}. Unknown groups → 422."""

    root: dict[str, int] = Field(
        default_factory=dict,
        description="Map of blind group id → position (0..100). Partial OK.",
    )


class BlindStateResponse(BaseModel):
    blinds: dict[str, int]
    written_at: datetime


def _session() -> Session:
    with session_scope() as s:
        yield s


def _validate_groups(body: dict[str, int]) -> None:
    if not body:
        raise HTTPException(
            status_code=422,
            detail="Body must include at least one group → position mapping.",
        )
    unknown = set(body) - set(BLIND_GROUPS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown blind group(s): {sorted(unknown)}. "
                f"Expected one of: {list(BLIND_GROUPS)}."
            ),
        )
    for group, pct in body.items():
        if not isinstance(pct, int) or pct < 0 or pct > 100:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Position for {group!r} must be an int in [0, 100]; got {pct!r}."
                ),
            )


@router.post("/state", response_model=BlindStateResponse, status_code=200)
def set_blind_state(
    payload: BlindStateBody,
    session: Annotated[Session, Depends(_session)],
) -> BlindStateResponse:
    """Record the user's claim about current blind state.

    Writes one ActuatorState row per group with ``source="manual"``. Idempotent
    in the sense that repeated calls with the same value just append rows —
    only the latest is read by DbCachedActuatorStateSource.
    """
    body = payload.root
    _validate_groups(body)

    now = datetime.now(tz=timezone.utc)
    rows = [
        ActuatorState(
            ts=now,
            actuator=f"blind:{group}",
            value=str(pct),
            source="manual",
        )
        for group, pct in body.items()
    ]
    repo.insert_actuator_states(session, rows)
    session.commit()

    # Echo the latest-per-group view (might include groups we didn't just set).
    latest = repo.latest_actuator_states(session)
    blinds = {}
    for key, row in latest.items():
        kind, _, name = key.partition(":")
        if kind == "blind":
            try:
                blinds[name] = int(row.value)
            except ValueError:
                continue
    return BlindStateResponse(blinds=blinds, written_at=now)


@router.get("/state", response_model=BlindStateResponse)
def get_blind_state(
    session: Annotated[Session, Depends(_session)],
) -> BlindStateResponse:
    """Latest-per-group view of blind state from the DB."""
    latest = repo.latest_actuator_states(session)
    blinds: dict[str, int] = {}
    most_recent_ts = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for key, row in latest.items():
        kind, _, name = key.partition(":")
        if kind == "blind":
            try:
                blinds[name] = int(row.value)
            except ValueError:
                continue
            ts = row.ts if row.ts.tzinfo else row.ts.replace(tzinfo=timezone.utc)
            if ts > most_recent_ts:
                most_recent_ts = ts
    return BlindStateResponse(blinds=blinds, written_at=most_recent_ts)
