"""Home Assistant WebSocket integration.

Maintains a persistent WS connection to HA, subscribes to state_changed events,
serves the latest state per entity from an in-memory cache. Auto-reconnects on
disconnect with exponential backoff.

The `HomeAssistantSensorSource` adapter implements the `SensorSource` Protocol
(same shape as `ManualSensorSource`) so swapping it in is a one-line change in
the route handlers.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

from app.sensors.source import (
    CurrentActuatorState,
    OutdoorReading,
    SunshineReading,
    ZoneSensorReading,
)

log = logging.getLogger(__name__)


def _ws_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + "/api/websocket"
    return "ws://" + base[len("http://") :] + "/api/websocket"


class HAClient:
    """WS connection lifecycle. Cache survives reconnects."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token
        self._cache: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()
        self._next_id = 1

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def get_state(self, entity_id: str) -> dict[str, Any] | None:
        return self._cache.get(entity_id)

    def all_states(self) -> dict[str, dict[str, Any]]:
        return dict(self._cache)

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="ha-ws-client")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_and_serve()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._connected.clear()
                log.warning(
                    "HA WS connection failed (%s); retrying in %.1fs", e, backoff
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 30.0)

    async def _connect_and_serve(self) -> None:
        url = _ws_url(self.base_url)
        log.info("HA WS connecting to %s", url)
        async with ws_connect(url, max_size=8 * 1024 * 1024) as ws:
            # 1) Greeting.
            greeting = json.loads(await ws.recv())
            if greeting.get("type") != "auth_required":
                raise RuntimeError(f"unexpected greeting: {greeting}")
            # 2) Auth.
            await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            ack = json.loads(await ws.recv())
            if ack.get("type") != "auth_ok":
                raise RuntimeError(f"auth failed: {ack}")
            log.info("HA WS authenticated; HA version: %s", ack.get("ha_version"))
            # 3) Initial snapshot of all states.
            states_id = self._next_id
            self._next_id += 1
            await ws.send(json.dumps({"id": states_id, "type": "get_states"}))
            # 4) Subscribe to state_changed events.
            sub_id = self._next_id
            self._next_id += 1
            await ws.send(
                json.dumps(
                    {
                        "id": sub_id,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    }
                )
            )
            self._connected.set()
            # Now serve.
            while not self._stop.is_set():
                raw = await ws.recv()
                msg = json.loads(raw)
                etype = msg.get("type")
                if etype == "result":
                    if msg.get("id") == states_id and msg.get("success"):
                        result = msg.get("result") or []
                        for s in result:
                            eid = s.get("entity_id")
                            if eid:
                                self._cache[eid] = s
                        log.info(
                            "HA WS initial snapshot: %d entities cached",
                            len(self._cache),
                        )
                    elif not msg.get("success"):
                        log.warning("HA WS command failed: %s", msg)
                elif etype == "event":
                    data = msg.get("event", {}).get("data", {}) or {}
                    new_state = data.get("new_state")
                    if new_state and "entity_id" in new_state:
                        self._cache[new_state["entity_id"]] = new_state


class HomeAssistantSensorSource:
    """Reads zone temp/humidity from HA via the cached HAClient.

    `entity_map` maps zone_id → {temp: entity_id, humidity?: entity_id}.
    """

    def __init__(
        self,
        client: HAClient,
        entity_map: dict[str, dict[str, str]],
    ) -> None:
        self.client = client
        self.entity_map = entity_map

    def latest(self) -> dict[str, ZoneSensorReading]:
        out: dict[str, ZoneSensorReading] = {}
        for zone, mapping in self.entity_map.items():
            temp_id = mapping.get("temp")
            if not temp_id:
                continue
            temp_state = self.client.get_state(temp_id)
            if temp_state is None:
                continue
            try:
                temp_c = float(temp_state["state"])
            except (TypeError, ValueError, KeyError):
                continue
            humidity_pct: float | None = None
            humid_id = mapping.get("humidity")
            if humid_id:
                hs = self.client.get_state(humid_id)
                if hs is not None:
                    try:
                        humidity_pct = float(hs["state"])
                    except (TypeError, ValueError, KeyError):
                        pass
            ts = _parse_ts(temp_state.get("last_updated"))
            out[zone] = ZoneSensorReading(
                zone=zone,
                ts=ts,
                temp_c=temp_c,
                humidity_pct=humidity_pct,
                lux_indoor=None,
            )
        return out


def _parse_ts(s: str | None) -> datetime:
    if s is None:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=timezone.utc)


class HomeAssistantSunshineSource:
    """SW glazing lux from HA (Phase 2: Aqara Light Sensor T1)."""

    def __init__(self, client: HAClient, entity_id: str) -> None:
        self.client = client
        self.entity_id = entity_id

    def latest(self) -> SunshineReading | None:
        if not self.entity_id:
            return None
        s = self.client.get_state(self.entity_id)
        if s is None:
            return None
        try:
            lux = float(s["state"])
        except (TypeError, ValueError, KeyError):
            return None
        return SunshineReading(
            ts=_parse_ts(s.get("last_updated")),
            lux=lux,
            scale=None,  # real sensor reading, not the manual 0–5 scale
        )


class HomeAssistantCoverSource:
    """Reads blind state from HA cover.* entities (Phase 2: Tahoma via Overkiz).

    `blind_groups` maps our internal group id → list of HA cover entity ids.
    When multiple entities map to one group (e.g. left + right bedroom blinds),
    their positions are averaged.

    Position semantics conversion:
      - HA cover.current_position: 100 = fully open, 0 = fully closed
      - Our blind_pct:             100 = fully down (closed), 0 = fully up (open)
    These are inverted; conversion is `our_pct = 100 - ha_position`.
    """

    def __init__(self, client: HAClient, blind_groups: dict[str, list[str]]) -> None:
        self.client = client
        self.blind_groups = blind_groups

    def latest(self) -> CurrentActuatorState:
        out_blinds: dict[str, int] = {}
        for group, entities in self.blind_groups.items():
            positions: list[int] = []
            for eid in entities:
                state = self.client.get_state(eid)
                if state is None:
                    continue
                attrs = state.get("attributes") or {}
                ha_pos = attrs.get("current_position")
                if ha_pos is None:
                    # Fallback: derive from coarse string state.
                    s = state.get("state")
                    if s == "closed":
                        ha_pos = 0
                    elif s == "open":
                        ha_pos = 100
                    else:
                        # 'opening' / 'closing' / 'unknown' / 'unavailable' → skip
                        continue
                try:
                    ha_pos_i = int(float(ha_pos))
                except (TypeError, ValueError):
                    continue
                ha_pos_i = max(0, min(100, ha_pos_i))
                # Invert: HA 100=open ↔ our 100=down.
                positions.append(100 - ha_pos_i)
            if positions:
                out_blinds[group] = sum(positions) // len(positions)
        return CurrentActuatorState(blind_pct=out_blinds, window_open={})


class HomeAssistantOutdoorSource:
    """Single-sensor outdoor microclimate reader (Phase 2: SwitchBot)."""

    def __init__(self, client: HAClient, mapping: dict[str, str]) -> None:
        self.client = client
        self.temp_entity = mapping.get("temp", "")
        self.humidity_entity = mapping.get("humidity", "")

    def latest(self) -> OutdoorReading | None:
        if not self.temp_entity:
            return None
        ts = self.client.get_state(self.temp_entity)
        if ts is None:
            return None
        try:
            temp_c = float(ts["state"])
        except (TypeError, ValueError, KeyError):
            return None
        humidity_pct: float | None = None
        if self.humidity_entity:
            hs = self.client.get_state(self.humidity_entity)
            if hs is not None:
                try:
                    humidity_pct = float(hs["state"])
                except (TypeError, ValueError, KeyError):
                    pass
        return OutdoorReading(
            ts=_parse_ts(ts.get("last_updated")),
            temp_c=temp_c,
            humidity_pct=humidity_pct,
        )
