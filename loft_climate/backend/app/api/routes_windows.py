"""User-asserted window state.

Why this exists: casement windows have no HA integration — no contact sensor,
no smart actuator. Until v0.12.0, `current_state.windows` was always empty,
which meant ActionPanel couldn't show "currently open / closed" annotations
for windows and red-urgency window pushes kept re-firing every 30 min even
after the user had acted on them. This route mirrors v0.9.0's
``/api/blinds/state`` for windows: writes go to ``actuator_state`` with
``source="manual"``, and the existing DbCachedActuatorStateSource picks
them up automatically.

Endpoints
---------
- ``POST /api/windows/state``  — set one or more zones in one call
- ``GET  /api/windows/state``  — read the current latest-per-zone view

Zone ids: ``mezzanine``, ``downstairs``, ``ceiling_apex``, ``bedroom``
(matches engine WINDOW_ZONES). Value semantics: ``true`` = open,
``false`` = closed. The dashboard's ALL-OPEN and ALL-CLOSED bulk buttons
send the same value for every zone.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, RootModel, StrictBool
from sqlalchemy.orm import Session

from app.db import repo
from app.db.models import ActuatorState
from app.db.session import session_scope
from app.engine.types import WINDOW_ZONES

router = APIRouter(prefix="/api/windows", tags=["windows"])


class WindowStateBody(RootModel[dict[str, StrictBool]]):
    """A partial dict of {zone: is_open}. Unknown zones → 422.

    Uses StrictBool so the schema rejects coercion sources like ``1`` /
    ``0`` / ``"true"`` — only real JSON booleans pass. The UI sends real
    booleans; if some future caller can't, they can switch to lax bool
    here, but explicit > clever beats silently accepting "open"=1.
    """

    root: dict[str, StrictBool] = Field(
        default_factory=dict,
        description="Map of zone id → is_open (true = open, false = closed). Partial OK.",
    )


class WindowStateResponse(BaseModel):
    windows: dict[str, bool]
    written_at: datetime


def _session() -> Session:
    with session_scope() as s:
        yield s


def _validate_zones(body: dict[str, bool]) -> None:
    if not body:
        raise HTTPException(
            status_code=422,
            detail="Body must include at least one zone → is_open mapping.",
        )
    unknown = set(body) - set(WINDOW_ZONES)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown window zone(s): {sorted(unknown)}. "
                f"Expected one of: {list(WINDOW_ZONES)}."
            ),
        )
    # Pydantic RootModel[dict[str, bool]] already enforces bool. This is a
    # defensive secondary check in case future schema changes loosen the type.
    for zone, is_open in body.items():
        if not isinstance(is_open, bool):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Value for {zone!r} must be a boolean; got {is_open!r}."
                ),
            )


@router.post("/state", response_model=WindowStateResponse, status_code=200)
def set_window_state(
    payload: WindowStateBody,
    session: Annotated[Session, Depends(_session)],
) -> WindowStateResponse:
    """Record the user's claim about current window state.

    Writes one ActuatorState row per zone with ``source="manual"``. Idempotent
    in the sense that repeated calls with the same value just append rows —
    only the latest is read by DbCachedActuatorStateSource.
    """
    body = payload.root
    _validate_zones(body)

    now = datetime.now(tz=timezone.utc)
    rows = [
        ActuatorState(
            ts=now,
            actuator=f"window:{zone}",
            value="open" if is_open else "closed",
            source="manual",
        )
        for zone, is_open in body.items()
    ]
    repo.insert_actuator_states(session, rows)
    session.commit()

    # Echo the latest-per-zone view (might include zones we didn't just set).
    latest = repo.latest_actuator_states(session)
    windows: dict[str, bool] = {}
    for key, row in latest.items():
        kind, _, name = key.partition(":")
        if kind == "window":
            windows[name] = row.value == "open"
    return WindowStateResponse(windows=windows, written_at=now)


@router.get("/state", response_model=WindowStateResponse)
def get_window_state(
    session: Annotated[Session, Depends(_session)],
) -> WindowStateResponse:
    """Latest-per-zone view of window state from the DB."""
    latest = repo.latest_actuator_states(session)
    windows: dict[str, bool] = {}
    most_recent_ts = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for key, row in latest.items():
        kind, _, name = key.partition(":")
        if kind == "window":
            windows[name] = row.value == "open"
            ts = row.ts if row.ts.tzinfo else row.ts.replace(tzinfo=timezone.utc)
            if ts > most_recent_ts:
                most_recent_ts = ts
    return WindowStateResponse(windows=windows, written_at=most_recent_ts)
