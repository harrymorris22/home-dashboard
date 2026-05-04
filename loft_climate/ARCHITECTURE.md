# Architecture — Phase 2 Migration Path

Phase 1 is hardware-free. Phase 2 swaps the manual sensor source for a Home
Assistant feed and lets HA actuate the blinds. The engine, weather, sun
calculator, history service, and entire frontend are unchanged across the
boundary.

## The abstraction line

[`backend/app/sensors/source.py:SensorSource`](backend/app/sensors/source.py)
is a Protocol. Phase 1 has one impl,
[`ManualSensorSource`](backend/app/sensors/manual.py), which reads from
SQLite. Phase 2 adds `HomeAssistantSensorSource` which subscribes to MQTT
and writes through to the same `Reading` table — so history is seamless
across cutover.

```
                        ┌─────────────────────┐
                        │  SensorSource       │   <- Protocol (Phase 2 swap)
                        └─────────────────────┘
                          ▲                ▲
              ┌───────────┘                └─────────────┐
              │                                          │
   ManualSensorSource                       HomeAssistantSensorSource
   (Phase 1: reads latest_per_zone          (Phase 2: subscribes to MQTT,
    from manual entries in DB)               writes Readings to same DB)
```

`SnapshotBuilder` takes a `SensorSource` — it doesn't care which impl. The
engine takes a `Snapshot` — it doesn't care where the sensors came from.

## Hardware (already purchased)

- 4× Aqara Temperature & Humidity Sensor T1 (Zigbee) — mezzanine,
  downstairs, ceiling apex, bedroom.
- 1× Aqara Light Sensor T1 (Zigbee) — stuck inside SW window.
- 1× SwitchBot Indoor/Outdoor Meter (Bluetooth) — outdoor, mounted in shaded
  position.
- 1× Raspberry Pi 5 (4 GB) — running Home Assistant OS.
- 1× SONOFF ZBDongle-P (TI CC2652P) — Zigbee coordinator + USB extension.
- Tahoma blinds (already paired with HA).

## Phase 2 transport — MQTT (recommended), WebSocket (alt), REST (fallback)

**MQTT (primary).** HA's MQTT integration publishes sensor state changes to
a broker; backend subscribes via `aiomqtt`. Sub-second freshness, native
reconnect, easiest to extend ("react when bedroom hits 25°C" eventually).

**WebSocket.** HA's native WS API gives state changes too; no broker needed.
Pick this if you don't already run a broker. Auth via long-lived access
token from `/profile/security` in HA.

**REST polling (30–60 s).** Pure fallback; wastes cycles but always works if
nothing else does. Only useful as a development crutch.

## Phase 2 wiring steps

1. Add `app/sensors/homeassistant.py` implementing `SensorSource`.
2. Add to `app/settings.py`:
   - `sensor_backend: Literal["manual", "ha_mqtt", "ha_ws", "ha_rest"] = "manual"`
   - `ha_base_url`, `ha_token`, `ha_mqtt_url`, `ha_entity_map`
3. Wire `app/main.py` to pick the source based on `sensor_backend`.
4. Manual entry endpoint stays — becomes a "manual override" path
   (`source="manual_override"`) for outages.
5. The HA source writes through to the same `Reading` table on each update,
   so history stays continuous.

## Phase 2 automations — HA YAML examples (TODO T6)

The original spec lists seven Phase 2 automations. Skeletons below are
illustrative; see [TODOS.md](TODOS.md) T6 for full implementation.

### 1. Pre-emptive shading

```yaml
automation:
  - alias: Pre-emptive shading
    trigger:
      - platform: numeric_state
        entity_id: weather.london
        attribute: forecast.0.temperature
        above: 22
    condition:
      - condition: numeric_state
        entity_id: sun.sun
        attribute: azimuth
        above: 135
      - condition: numeric_state
        entity_id: sun.sun
        attribute: azimuth
        below: 270
      - condition: numeric_state
        entity_id: sun.sun
        attribute: elevation
        above: 10
      - condition: numeric_state
        entity_id: sensor.sw_lux
        above: 8000
    action:
      - service: cover.set_cover_position
        target:
          entity_id:
            - cover.tahoma_mezz
            - cover.tahoma_downstairs
        data:
          position: 0
```

### 2. Bedroom early closure

```yaml
automation:
  - alias: Bedroom early close on heatwave days
    trigger:
      - platform: time
        at: "13:00:00"
    condition:
      - condition: numeric_state
        entity_id: weather.london
        attribute: forecast.0.temperature
        above: 24
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.tahoma_bedroom
```

### 3. Solar gain in winter

```yaml
automation:
  - alias: Winter solar gain
    trigger:
      - platform: state
        entity_id: sensor.house_avg_temp
    condition:
      - condition: numeric_state
        entity_id: sensor.house_avg_temp
        below: 19
      - condition: numeric_state
        entity_id: sensor.outdoor_temp
        below: 12
      - condition: state
        entity_id: binary_sensor.sun_on_sw
        state: "on"
    action:
      - service: cover.open_cover
        target:
          entity_id:
            - cover.tahoma_mezz
            - cover.tahoma_downstairs
```

### 4. Night purge notification

```yaml
automation:
  - alias: Notify night purge
    trigger:
      - platform: numeric_state
        entity_id: sensor.house_avg_temp
        above: 24
    condition:
      - condition: time
        after: "18:00:00"
        before: "23:00:00"
      - condition: template
        value_template: >
          {{ states('sensor.outdoor_temp') | float
             < states('sensor.house_avg_temp') | float - 2 }}
    action:
      - service: notify.mobile_app
        data:
          title: Open windows
          message: Outdoor cooler than indoor — purge heat now.
```

### 5–7

Morning lockdown notification, pre-cool prompt, combo prompt — same template
shape as #4. Include in TODO T6 implementation.

## What does NOT change in Phase 2

- `app/engine/*` — every rule, the classifier, combine, hysteresis,
  reasoning, types.
- `app/weather/*`, `app/sun/*`, `app/history/*`, `app/config/*`.
- `app/snapshot/builder.py` — its `sensor_source` argument is the only
  Protocol-typed input.
- `app/api/routes_state.py` — picks the source via DI, but the response
  shape is identical.
- The entire `frontend/` directory.

That's the win.

## Open Phase 2 decisions (parked, not blocking)

- **Override execution.** `POST /api/state/override` returns 501 in Phase 1.
  Phase 2 wires it to `cover.set_position` + a temporary rule-suppression
  flag. See [TODOS.md](TODOS.md) T3.
- **History compaction.** With 1 reading/min × 4 zones × 365 days = 2.1 M
  rows, a downsample cron is needed. See [TODOS.md](TODOS.md) T2.
- **Per-zone azimuth windows for self-shading.** Real London-terrace
  glazing has neighbour shading; the lux-confirm predicate masks this in
  Phase 1, structural fix in Phase 2/3. See [TODOS.md](TODOS.md) T5.
