"""Single source of truth for the dashboard's full state assembly.

Both `routes_state.get_state` and `PushScheduler._tick` call this. Eliminates
the snapshot-path drift class — when sensor sources, response fields, or
weather adapters change, both consumers move in lockstep.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config.loader import load_config
from app.config.schema import ConfigV1
from app.engine.engine import decide
from app.engine.forecast import project_actions
from app.engine.types import DashboardRecommendation, Snapshot
from app.sensors.composite import (
    CompositeActuatorStateSource,
    CompositeSensorSource,
)
from app.sensors.homeassistant import (
    HomeAssistantCoverSource,
    HomeAssistantOutdoorSource,
    HomeAssistantSensorSource,
    HomeAssistantSunshineSource,
)
from app.sensors.manual import (
    ManualActuatorStateSource,
    ManualSensorSource,
    ManualSunshineSource,
)
from app.settings import Settings, get_settings
from app.snapshot.builder import SnapshotBuilder


@dataclass(frozen=True)
class StateBundle:
    cfg: ConfigV1
    snap: Snapshot
    rec: DashboardRecommendation
    next_actions: list[dict[str, Any]]


def _build_sensor_source(session: Session, ha_client, settings: Settings):
    manual = ManualSensorSource(session)
    if ha_client is not None and settings.ha_entity_map:
        ha = HomeAssistantSensorSource(ha_client, settings.ha_entity_map)
        return CompositeSensorSource(ha, manual)
    return manual


async def build_full_state(session: Session, ha_client) -> StateBundle:
    """Assemble the snapshot the way `/api/state` does. Pure I/O orchestration —
    no engine logic here."""
    cfg = load_config()
    settings = get_settings()
    sensor_source = _build_sensor_source(session, ha_client, settings)

    outdoor_source = None
    if ha_client is not None and settings.ha_outdoor_entities:
        outdoor_source = HomeAssistantOutdoorSource(ha_client, settings.ha_outdoor_entities)

    sunshine_source = ManualSunshineSource(session)
    if ha_client is not None and settings.ha_sunshine_entity:
        ha_sun = HomeAssistantSunshineSource(ha_client, settings.ha_sunshine_entity)
        if ha_sun.latest() is not None:
            sunshine_source = ha_sun

    # Actuator state: HA cover source preferred (blind position from Tahoma),
    # manual fills the rest (windows are physical casements, not on HA).
    manual_actuator = ManualActuatorStateSource(session)
    if ha_client is not None and settings.ha_blind_entities:
        ha_cover = HomeAssistantCoverSource(ha_client, settings.ha_blind_entities)
        actuator_source = CompositeActuatorStateSource(ha_cover, manual_actuator)
    else:
        actuator_source = manual_actuator

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


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)
