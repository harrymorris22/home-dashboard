# TODOS

Deferred work captured during `/plan-eng-review`. Each entry has the
context, the why, and any blocking dependency.

## T1 — Lux calibration script + UI button

**What.** A small Python script + dashboard button that pulls recent lux
readings from `Reading`, joins them to computed sun azimuth at each
timestamp, plots a histogram, and suggests a value for
`sun_on_sw.lux_indoor_direct_threshold` based on the valley between
"direct beam" and "diffuse" clusters.

**Why.** Phase 1 ships defaults `direct=8000` / `diffuse=2000` lux. Real
values depend on glazing transmittance, sensor placement, distance to glass,
and adjacent buildings. Without calibration the `is_sun_on_sw` predicate
either over- or under-fires.

**Depends on.** ~1 week of data collected; the sun calculator already exists.

**Approx surface.** `backend/scripts/calibrate_lux.py` (~50 lines) +
`/api/calibrate/lux` returning the histogram + a button on `/config`.

## T2 — History compaction cron (Phase 2)

**What.** Scheduled job (cron or APScheduler) that downsamples `Reading`
rows: keep raw < 30 days, 5-min averages 30 d–1 yr, daily aggregates
beyond.

**Why.** Phase 2 cadence (1 reading/min × 4 zones × 365 days = ~2.1 M rows)
will degrade query latency without compaction. Phase 1 doesn't need this
(manual entry is sparse).

**Depends on.** Phase 2 hardware integration writing readings at 1-min
cadence.

**Retention thresholds (decide once, then commit):**

- raw rows: 30 days
- 5-min averages: 30 days → 1 year
- daily aggregates: > 1 year

## T3 — Manual user-override hook (Phase 2 wire-up)

**What.** Wire `POST /api/state/override {actuator, value, expires_at}` to
call HA service `cover.set_position` and set a temporary rule-suppression
flag in `engine.combine()`.

**Why.** "I'm cooking, ignore blind automation for 2 hours." Phase 1
reserves the route at 501. Phase 2 needs it live.

**Depends on.** `HomeAssistantSensorSource` impl + a HA service-call
client.

## T4 — Richer stack-effect physics (Phase 3 quality)

**What.** Replace the +4°C heuristic in `apex_stack_vent` with a model
that pairs an inlet (low) with an outlet (high), reasons about wind
direction relative to the SW face, and considers neutral pressure level.

**Why.** Outside-voice reviewer noted the +4°C heuristic can mis-fire
under unfavourable wind directions. Diminishing returns vs. simpler rule
unless real data shows it failing.

**Depends on.** Phase 1 + 2 deployed; data showing the heuristic
mis-firing in practice.

## T5 — Per-zone azimuth windows for self-shading

**What.** Replace the global `[135°, 270°]` azimuth window with per-zone
ranges:

```jsonc
"zones": {
  "bedroom": {
    ...,
    "sun_window": { "azimuth_min": 200, "azimuth_max": 260 }
  }
}
```

Defaults to the global value when unset.

**Why.** Real London-terrace SW glazing has neighbour shading. The
bedroom may not see direct sun until 14:00 even though the mezzanine sees
it from 12:00.

**Depends on.** 1–2 weeks of lux data per zone for empirical calibration.

## T6 — Phase 2 ARCHITECTURE.md HA YAML examples

**What.** Flesh out the full YAML for the seven Phase 2 automations
listed in the spec (pre-emptive shading, bedroom early closure, solar
gain in winter, night purge, morning lockdown, pre-cool, combo prompt).
Skeletons exist in [ARCHITECTURE.md](ARCHITECTURE.md); fill in entity
IDs once HA is set up.

**Why.** Spec-mandated deliverable. Easier to write the YAML when entity
names are stable and the broker is configured.

**Depends on.** Phase 1 wrapping + HA integration approach (MQTT
chosen).
