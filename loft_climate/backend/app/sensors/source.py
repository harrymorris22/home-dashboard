from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ZoneSensorReading:
    zone: str
    ts: datetime
    temp_c: float
    humidity_pct: float | None
    lux_indoor: float | None  # legacy per-zone slot — kept for forward compat with Phase 2 if needed


@dataclass(frozen=True)
class SunshineReading:
    ts: datetime
    lux: float
    scale: int | None  # 0–5 if from the manual scale, None if from a real sensor


@dataclass(frozen=True)
class CurrentActuatorState:
    """The latest known physical state of every actuator."""

    blind_pct: dict[str, int]  # group → 0..100
    window_open: dict[str, bool]  # zone → True/False


@dataclass(frozen=True)
class OutdoorReading:
    """A real outdoor microclimate measurement (Phase 2: SwitchBot on the building)."""

    ts: datetime
    temp_c: float
    humidity_pct: float | None


class SensorSource(Protocol):
    """Per-zone temp/humidity reader.

    HA-first: HomeAssistantSensorSource subscribes to Aqara WS state. Falls
    back to DbCachedSensorSource (latest persisted row) when HA is offline.
    """

    def latest(self) -> dict[str, ZoneSensorReading]:
        ...


class SunshineSource(Protocol):
    """SW-glazing light reader.

    HomeAssistantSunshineSource (Aqara T1) when HA is up, otherwise
    DbCachedSunshineSource serves the latest persisted row.
    """

    def latest(self) -> SunshineReading | None:
        ...


class ActuatorStateSource(Protocol):
    """Latest known physical state of blinds + windows.

    HomeAssistantCoverSource (Tahoma covers) for blinds when HA is up;
    DbCachedActuatorStateSource for HA-down recovery and any actuators
    HA doesn't track (e.g. casement windows).
    """

    def latest(self) -> CurrentActuatorState:
        ...


class OutdoorSource(Protocol):
    """Real-time outdoor microclimate sensor.

    Optional. When present, overrides OWM's temp / humidity / feels_like fields
    on the WeatherSnapshot since a sensor on the building is more accurate than
    a forecast gridcell. OWM still owns wind, cloud, UVI, sunrise/sunset, etc.
    """

    def latest(self) -> OutdoorReading | None:
        ...
