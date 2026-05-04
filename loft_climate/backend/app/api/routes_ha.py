"""Home Assistant introspection endpoints.

Phase 2 helpers. `/api/ha/entities` lists what HA exposes so the user can pick
which entity_ids map to which zone in the dashboard config.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/ha", tags=["home-assistant"])


@router.get("/status")
def ha_status(request: Request):
    client = getattr(request.app.state, "ha_client", None)
    if client is None:
        return {"enabled": False, "connected": False, "cached_entities": 0}
    return {
        "enabled": True,
        "connected": client.connected,
        "cached_entities": len(client.all_states()),
        "base_url": client.base_url,
    }


@router.get("/entities")
def ha_entities(
    request: Request,
    domain: str = "sensor",
    only_climate: bool = True,
):
    """List entities cached from HA.

    `domain=sensor` filters to sensors (most useful for our temp/humid/lux pull).
    `only_climate=true` further restricts to entities whose `device_class` or
    `unit_of_measurement` looks like temperature, humidity, or illuminance —
    which is what we actually want to map to zones.
    """
    client = getattr(request.app.state, "ha_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="HA client not configured (check HA_BASE_URL + HA_TOKEN in .env)",
        )

    items: list[dict] = []
    for eid, state in client.all_states().items():
        if domain and not eid.startswith(f"{domain}."):
            continue
        attrs = state.get("attributes") or {}
        unit = (attrs.get("unit_of_measurement") or "").strip()
        device_class = attrs.get("device_class")

        if only_climate:
            climate_units = {"°C", "°F", "%", "lx"}
            climate_classes = {"temperature", "humidity", "illuminance"}
            if unit not in climate_units and device_class not in climate_classes:
                continue

        items.append(
            {
                "entity_id": eid,
                "state": state.get("state"),
                "unit": unit,
                "device_class": device_class,
                "friendly_name": attrs.get("friendly_name"),
                "last_updated": state.get("last_updated"),
            }
        )
    items.sort(key=lambda x: (x.get("device_class") or "", x["entity_id"]))
    return {"connected": client.connected, "count": len(items), "items": items}
