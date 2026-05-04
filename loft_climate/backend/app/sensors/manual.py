from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import repo
from app.sensors.source import (
    CurrentActuatorState,
    SunshineReading,
    ZoneSensorReading,
)


class ManualSensorSource:
    """Reads the latest manually-entered Reading per zone."""

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


class ManualSunshineSource:
    """Reads the latest manually-entered Sunshine row (0–5 scale → lux)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> SunshineReading | None:
        row = repo.latest_sunshine(self.session)
        if row is None:
            return None
        return SunshineReading(ts=row.ts, lux=row.lux, scale=row.scale)


class ManualActuatorStateSource:
    """Reads the latest manually-entered physical state for blinds + windows."""

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
