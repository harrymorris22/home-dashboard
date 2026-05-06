"""Compose multiple SensorSources / ActuatorStateSources.

The first source wins per key; missing keys fall through to the next source.
Used during the Phase 2 cutover where some signals come from HA and others
remain manual.
"""
from __future__ import annotations

from app.sensors.source import CurrentActuatorState, ZoneSensorReading


class CompositeSensorSource:
    def __init__(self, *sources: object) -> None:
        # Each `source` must implement `.latest() -> dict[str, ZoneSensorReading]`.
        self.sources = sources

    def latest(self) -> dict[str, ZoneSensorReading]:
        out: dict[str, ZoneSensorReading] = {}
        for src in self.sources:
            data = src.latest()  # type: ignore[attr-defined]
            for zone, reading in data.items():
                if zone not in out:
                    out[zone] = reading
        return out


class CompositeActuatorStateSource:
    """First source wins per actuator. Phase 2: pass HA cover source first
    (knows blind positions), then manual source (still owns windows + any
    blinds not yet wired to HA)."""

    def __init__(self, *sources: object) -> None:
        self.sources = sources

    def latest(self) -> CurrentActuatorState:
        blinds: dict[str, int] = {}
        windows: dict[str, bool] = {}
        for src in self.sources:
            state: CurrentActuatorState = src.latest()  # type: ignore[attr-defined]
            for group, pct in state.blind_pct.items():
                if group not in blinds:
                    blinds[group] = pct
            for zone, is_open in state.window_open.items():
                if zone not in windows:
                    windows[zone] = is_open
        return CurrentActuatorState(blind_pct=blinds, window_open=windows)
