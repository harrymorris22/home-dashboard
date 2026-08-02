# Changelog

## 0.20.2

- Fix: outdoor sensor calibration was failing with HA 400 Bad Request
  every time (weekly tick and Recalibrate button both). The HA
  history REST URL contained raw `+00:00` timezone suffixes; HA's
  query-string parser decoded `+` as a space per WHATWG rules,
  corrupting `end_time` and the path timestamp. Fix: normalise
  timestamps to Z-suffixed UTC and URL-encode the path segment.
  Frontend "No overlapping history yet" message will now go away
  as soon as the first successful fit persists.

## 0.20.1

- Fix: clicking "Recalibrate now" on the Config page blanked the whole
  page. POST /api/outdoor/bias returned only `{calibration}` while GET
  returned `{calibration, settings}`; the frontend fed the POST
  response into its SWR cache, `settings` disappeared, and the next
  render crashed. Backend now returns the same envelope from both
  routes; frontend re-fetches via GET after a successful POST and
  falls back to defensive setting defaults so a partial payload can
  never blank the page again.

## 0.20.0

- Outdoor SwitchBot sensor now bias-corrected before the rules see it.
  The sensor overshoots by up to +8°C on sunny mornings when direct sun
  hits its casing; the app subtracts an hour-of-day bias curve scaled
  by current cloud cover. Overnight microclimate offset (~+1.5°C) is
  preserved as real. This unblocks morning cross-vent recommendations
  that were previously silenced by the inflated reading.
- Bias curve auto-refits weekly (or on first startup) by joining
  SwitchBot history from HA Recorder with Met.no history from the local
  weather_cache. New "Outdoor sensor calibration" card on the Config
  page shows the current curve as a per-hour bar chart, when it was
  last fitted, and a "Recalibrate now" button that forces a refit.
- New endpoints: `GET /api/outdoor/bias` returns the fitted curve +
  correction settings, `POST /api/outdoor/bias` triggers a refit.
- Backwards-compat: correction defaults to on. Set
  `outdoor.correction = sensor_only` in config to opt out and use the
  raw sensor reading.

## 0.19.0

- New `/api/weather/history?days=N` endpoint returns every cached Met.no
  snapshot from the last N days (capped at 90). Enables plotting the
  outdoor sensor against Met.no over weeks to see when and how the
  sensor over-reads. Payload is raw fetches (~1 per 10 minutes); the
  client aggregates to whatever bucket it needs.

## 0.18.0

- Cross-ventilation now fires per zone instead of house-wide. When
  Office and Apex are hotter than outdoor but Bedroom is cooler, the
  hot zones get real "Open X window" tasks in the checklist and the
  cool zone stays silent with "opening would import heat". Previously
  the whole house was silenced if the average didn't cross the vent
  threshold, hiding the per-zone opportunity.
- Rule engine gained per-zone reasoning support so each window row's
  explanation carries that zone's own indoor temp.

## 0.17.0

- Window "no change" rows now report each zone's own indoor temp
  instead of the house average, so the reasoning line for the office
  no longer claims "indoor 28°C" when the office is actually 30°C.
- When a zone is meaningfully hotter than outdoor but the house-wide
  vent rule stayed silent (cooler zones drag the average down), the
  row now suggests opening manually to vent instead of falsely
  claiming that opening would import heat.

## 0.16.0

- "What to do" panel becomes a task checklist. One row per physical
  action, verb-first, with a one-line hint. Rows auto-tick when the
  blind/window state you mark below matches the recommendation, so the
  existing state controls double as the "done" mechanism. Undone rows
  sort by urgency then zone (windows before blinds); done rows sink
  below a divider with a "X/N done" count.

## 0.15.0

- Reasoning transparency: rules that silence themselves now explain why
  (e.g. "Weather offline — no outside data to decide") instead of
  disappearing without trace.

## 0.14.0

- Fix: a blinds-only rule no longer claims it will improve airflow.
  Reasoning text now matches the actuators the rule actually touches.

## 0.13.0

- Fix past-hour projections in the Next actions panel. Times in the
  past are now clamped to "now" rather than displayed as if scheduled.

## 0.12.0

- User-input window state from the dashboard. Mark each window
  open/closed to close the loop on ventilation recommendations.

## 0.11.0

- Tune `sun_on_glazing` geometry for the SE-facing loft. Fewer false
  positives at low sun angles.

## 0.10.0

- Blinds-aware sun-on-SW classification: if the blinds are already
  down, don't fire block-solar-gain again.

## 0.9.0

- User-input blind state from the dashboard. Mark each group so the
  recommendation engine has the current position to compare against.

## 0.8.0

- Pluggable weather provider with Met.no as the default (no API key
  required).

## 0.7.0

- Weather staleness contract: stale data no longer drives fresh
  recommendations. Missing-blind-state UI banner surfaces when Tahoma
  is offline.

## 0.6.0

- Strip legacy Entry + Simulate views. Slow tick now persists HA
  sensor readings straight to the local DB.

## 0.5.0

- Sports HUD redesign: light theme, Archivo Black display face,
  single accent reserved for RED urgency.

## 0.4.0

- Live blind state from Tahoma via the HA cover source.

## 0.3.1

- Fix PEM → raw base64url conversion before handing keys to
  pywebpush.

## 0.3.0

- PWA + Web Push notifications (iOS Safari).
