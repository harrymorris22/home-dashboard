"""Compose multiple SensorSources, preferring earlier ones per zone.

Used during the Phase 2 cutover when some zones are wired to HA and others
are still on manual entry. The first source's data wins per-zone; missing
zones fall through to the next source.
"""
from __future__ import annotations

from app.sensors.source import ZoneSensorReading


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
