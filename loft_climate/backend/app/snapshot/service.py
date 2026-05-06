"""Single source of truth for the dashboard's full state assembly.

Both `routes_state.get_state` and `PushScheduler._tick` call this. Eliminates
the snapshot-path drift class — when sensor sources, response fields, or
weather adapters change, both consumers move in lockstep.

Also exposes ``snapshot_to_rows`` — a pure transform from the assembled
StateBundle into ORM rows ready for insert. Used by the slow-tick
persistence path so History accumulates real HA-sourced data without a
separate ingestion service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config.loader import load_config
from app.config.schema import ConfigV1
from app.db.models import ActuatorState, Reading, Sunshine
from app.engine.engine import decide
from app.engine.forecast import project_actions
from app.engine.types import DashboardRecommendation, Snapshot
from app.sensors.composite import (
    CompositeActuatorStateSource,
    CompositeSensorSource,
)
from app.sensors.db_cached import (
    DbCachedActuatorStateSource,
    DbCachedSensorSource,
    DbCachedSunshineSource,
)
from app.sensors.homeassistant import (
    HomeAssistantCoverSource,
    HomeAssistantOutdoorSource,
    HomeAssistantSensorSource,
    HomeAssistantSunshineSource,
)
from app.settings import Settings, get_settings
from app.snapshot.builder import SnapshotBuilder

# Stamped onto every row written by the slow-tick snapshot persistence path.
# Pre-v0.6 rows still bear ``source="manual"`` from the deleted Entry form;
# queries don't filter on source so both coexist harmlessly.
SNAPSHOT_SOURCE = "ha"


@dataclass(frozen=True)
class StateBundle:
    cfg: ConfigV1
    snap: Snapshot
    rec: DashboardRecommendation
    next_actions: list[dict[str, Any]]


@dataclass(frozen=True)
class SnapshotRows:
    """ORM rows produced from a StateBundle, ready to insert."""

    readings: list[Reading]
    sunshine: Sunshine | None  # None when no SW lux source is available
    actuators: list[ActuatorState]  # only HA-known actuators (blinds today)


def _build_sensor_source(session: Session, ha_client, settings: Settings):
    fallback = DbCachedSensorSource(session)
    if ha_client is not None and settings.ha_entity_map:
        ha = HomeAssistantSensorSource(ha_client, settings.ha_entity_map)
        return CompositeSensorSource(ha, fallback)
    return fallback


async def build_full_state(session: Session, ha_client) -> StateBundle:
    """Assemble the snapshot the way `/api/state` does. Pure I/O orchestration —
    no engine logic here."""
    cfg = load_config()
    settings = get_settings()
    sensor_source = _build_sensor_source(session, ha_client, settings)

    outdoor_source = None
    if ha_client is not None and settings.ha_outdoor_entities:
        outdoor_source = HomeAssistantOutdoorSource(ha_client, settings.ha_outdoor_entities)

    sunshine_source = DbCachedSunshineSource(session)
    if ha_client is not None and settings.ha_sunshine_entity:
        ha_sun = HomeAssistantSunshineSource(ha_client, settings.ha_sunshine_entity)
        if ha_sun.latest() is not None:
            sunshine_source = ha_sun

    # Actuator state: HA cover source preferred (blind position from Tahoma),
    # DB-cached fills the rest (windows aren't on HA today; blinds fall back
    # to the last persisted row when HA is offline).
    fallback_actuator = DbCachedActuatorStateSource(session)
    if ha_client is not None and settings.ha_blind_entities:
        ha_cover = HomeAssistantCoverSource(ha_client, settings.ha_blind_entities)
        actuator_source = CompositeActuatorStateSource(ha_cover, fallback_actuator)
    else:
        actuator_source = fallback_actuator

    builder = SnapshotBuilder(
        session,
        sensor_source,
        cfg,
        sunshine_source=sunshine_source,
        actuator_state_source=actuator_source,
        outdoor_source=outdoor_source,
    )
    snap = await builder.build()
    rec = decide(snap)
    next_actions = project_actions(snap)
    return StateBundle(cfg=cfg, snap=snap, rec=rec, next_actions=next_actions)


def snapshot_to_rows(bundle: StateBundle, now: datetime) -> SnapshotRows:
    """Pure transform from a StateBundle to ORM rows.

    Skips zones whose HA entity returned nothing (the snapshot builder
    simply omits absent zones from `snap.zones`, so the comprehension is
    a no-op for those). Sunshine row is omitted when no SW lux source
    is available. Actuator rows are only emitted for blinds — windows
    are physical casements with no HA source.
    """
    readings = [
        Reading(
            ts=now,
            zone=zone,
            temp_c=reading.temp_c,
            humidity_pct=reading.humidity_pct,
            lux_indoor=reading.lux_indoor,
            source=SNAPSHOT_SOURCE,
        )
        for zone, reading in bundle.snap.zones.items()
        if reading is not None
    ]
    sunshine = (
        Sunshine(
            ts=now,
            lux=bundle.snap.sw_lux,
            scale=None,
            source=SNAPSHOT_SOURCE,
        )
        if bundle.snap.sw_lux is not None
        else None
    )
    actuators = [
        ActuatorState(
            ts=now,
            actuator=f"blind:{group}",
            value=str(pct),
            source=SNAPSHOT_SOURCE,
        )
        for group, pct in bundle.snap.current_blind.items()
    ]
    return SnapshotRows(readings=readings, sunshine=sunshine, actuators=actuators)


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)
