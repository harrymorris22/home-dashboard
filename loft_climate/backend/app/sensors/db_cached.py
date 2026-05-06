"""DB-cached sensor sources.

Each source returns the latest row per key from SQLite. Source-agnostic:
in v0.6+ those rows are written by the HA snapshot task in
PushScheduler._tick_slow with ``source="ha"``. Pre-v0.6 they were
written by the manual entry form with ``source="manual"``. Read path is
identical either way — we just hand back the freshest persisted row.

Used as the second arm of CompositeSensorSource: HA's in-memory cache
takes priority when fresh; this fallback covers HA-down windows by
serving the last persisted snapshot.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import repo
from app.sensors.source import (
    CurrentActuatorState,
    SunshineReading,
    ZoneSensorReading,
)


class DbCachedSensorSource:
    """Reads the latest Reading row per zone from the DB."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> dict[str, ZoneSensorReading]:
        out: dict[str, ZoneSensorReading] = {}
        for zone, row in repo.latest_per_zone(self.session).items():
            out[zone] = ZoneSensorReading(
                zone=zone,
                ts=row.ts,
                temp_c=row.temp_c,
                humidity_pct=row.humidity_pct,
                lux_indoor=row.lux_indoor,
            )
        return out


class DbCachedSunshineSource:
    """Reads the latest Sunshine row from the DB."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> SunshineReading | None:
        row = repo.latest_sunshine(self.session)
        if row is None:
            return None
        return SunshineReading(ts=row.ts, lux=row.lux, scale=row.scale)


class DbCachedActuatorStateSource:
    """Reads the latest physical actuator state per key from the DB."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> CurrentActuatorState:
        rows = repo.latest_actuator_states(self.session)
        blinds: dict[str, int] = {}
        windows: dict[str, bool] = {}
        for key, row in rows.items():
            kind, _, name = key.partition(":")
            if kind == "blind":
                try:
                    blinds[name] = int(row.value)
                except ValueError:
                    continue
            elif kind == "window":
                windows[name] = row.value == "open"
        return CurrentActuatorState(blind_pct=blinds, window_open=windows)
