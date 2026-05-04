# Loft Climate — Phase 1

A web dashboard that recommends per-zone blind positions and window open/closed
states for a SW-facing London loft (Canal Building). Phase 1 runs against
manually-entered sensor data so the rule logic can be validated before any
Aqara / Pi 5 / Home Assistant hardware arrives.

Phase 2 swaps the manual sensor source for a Home Assistant feed without
touching the engine, weather, sun, or any frontend code — see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Stack

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy 2.0 (sync) · SQLite (WAL) ·
  pydantic v2 · `astral` for sun position · `httpx` for OpenWeatherMap.
- **Frontend:** React + Vite + TypeScript · Tailwind (dark glassmorphism) ·
  Recharts · SWR.
- **Tests:** `pytest` (63 tests) · `vitest` (17 tests).

## Run it

### One-time setup

```bash
# Backend
cd backend
python3.12 -m venv .venv          # or use the .venv created during install
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd ../frontend
npm install

# Configuration
cp ../.env.example ../.env
# Edit ../.env and set OWM_API_KEY (One Call 3.0 — free 1000 calls/day).
```

### Day-to-day

```bash
# Terminal 1 — backend on :8000
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — frontend on :5173 (proxies /api → :8000)
cd frontend
npm run dev
```

Then open <http://127.0.0.1:5173>.

### Tests

```bash
cd backend && ./.venv/bin/pytest          # 63 tests
cd frontend && npm test                   # 17 tests
npm run build                             # type-check + production build
```

## Decision engine

The engine is **pure-functional**. `engine.decide(snapshot)` takes a
[`Snapshot`](backend/app/engine/types.py) (sensors + weather + sun + config +
time) and returns a [`DashboardRecommendation`](backend/app/engine/types.py).
Same input → same output. No I/O. No hidden state.

```
Snapshot ─► classify ─► Facts ─► run_rules ─► [RuleOutput] ─► combine ─► DashboardRecommendation
```

### Rule registry

Rules live in [backend/app/engine/rules.py](backend/app/engine/rules.py) as
plain `Rule` instances collected into an explicit `ALL_RULES` list — no
decorator-based auto-registration, so import order can never silently drop a
rule. `decide()` accepts a `rules=` parameter so tests can pass a subset.

Each rule has a `priority`. The matrix decomposes into independent
blind-rules + window-rules so they compose without contradiction:

| Scenario | Blind rule | Window rule | Priority |
|---|---|---|---|
| Hot + sunny + breeze | `block_solar_gain` | `cross_ventilate` | 80 |
| Hot + sunny + still | `block_solar_gain` | `seal_against_heat` | 80 |
| Hot + cloudy | `let_light_in` | (`cross_ventilate` if breeze, else neutral) | 80 |
| Cold + sunny | `harvest_solar` | `seal_for_warmth` | 80 |
| Cold + cloudy | `insulate_blinds` | `seal_for_warmth` | 80 |
| Post-sunset hot day | `release_blinds` | `night_purge` | 70 |
| Pre-dawn hot day | (skip — dark) | `pre_cool` | 70 |
| Bedtime + bedroom warm | bedroom blind down | bedroom window per outdoor | 90 |
| Bedroom ≥ 25°C @ bedtime | red urgency | force open if outdoor cooler | 100 |
| Apex > house_avg + 4°C, outdoor cooler | — | mezz window open (stack vent) | 75 |
| Rain / storm | (no change) | suppress all "open" recommendations | 110 |

### Conflict resolution

Within an actuator namespace (a blind group, a zone window), highest priority
wins. Equal-priority disagreement → `scenario="neutral"`, `urgency="amber"`,
both reasons surfaced. Per-zone rules (priority ≥ 90) always beat house-wide
rules for that zone.

Each rule's `predicate` and `produce` is **wrapped in try/except** in
[combine.py](backend/app/engine/combine.py) so a single buggy rule cannot brick
`/api/state` — failed rules log and surface in `recommendations.rule_errors`.

### Hysteresis (anti-flap)

After `combine()`, [hysteresis.py](backend/app/engine/hysteresis.py) reads the
most recent `RecommendationLog` per actuator. If the prior recommendation is
younger than `engine.dwell_minutes` (default 20), the prior value is held —
unless (a) the new urgency is `red` (safety always wins) or (b) the prior is
older than `engine.stale_after_minutes` (default 90). Critical because each
toggle of a manual blind / window is a human cost.

### Apparent temperature

[heat_index.py](backend/app/engine/heat_index.py) uses a **simple linear
humidity correction** valid across 18–32°C, not the NWS Rothfusz polynomial
(which is only valid ≥ 26.7°C and degenerates to ~T below). Returns ~T in dry
air, +1–2°C in muggy 24°C / 70% RH.

### Degraded mode (no weather)

If the OpenWeatherMap fetch fails on cold start (no cached row),
`Snapshot.weather = None`. Indoor-only rules (`bedroom_too_hot_safety`,
`apex_stack_vent`, `bedtime_prep`) still fire. The dashboard surfaces a
"Weather offline" banner. Manual entry is never blocked by upstream outages.

## Threshold config

Edit [backend/data/config.json](backend/data/config.json) (created on first
run from `config.default.json`) or use the `/config` route in the dashboard.
A pydantic `model_validator` enforces business invariants
(`comfort_min < comfort_max`, etc.); bad edits fail loud at startup or with a
422 from `PUT /api/config`.

Notable thresholds you'll likely tune:

- `sun_on_sw.lux_indoor_direct_threshold` (default `8000`) — calibrate after
  ~1 week of data; see [TODOS.md](TODOS.md) T1.
- `engine.dwell_minutes` — increase if recommendations still flap, decrease
  if you find yourself ignoring stale advice.
- `zones.*.comfort_max` — single biggest knob.

## Verification — Phase 1 acceptance

1. `uvicorn app.main:app --reload` boots; `GET /healthz` returns `{ok: true}`.
2. With no OWM key set: `GET /api/state` returns 200 with `weather: null` and
   the dashboard renders an offline banner. Manual entry still works.
3. With an OWM key: `POST /api/weather/refresh` populates the cache; the
   dashboard's `WeatherStrip` shows fresh values.
4. Submit hot values via `/entry`; all four zone cards update on next refresh.
5. Walk every matrix row via `/simulate` (dropdown of named scenarios) and
   confirm the badge + blind percentages + window states match the table above.
6. `PUT /api/config` with `comfort_min > comfort_max` returns 422.
7. Submit 6+ entries spaced across a day; `/history` plots all four zones,
   zone-toggle pills work, metric switch (temp/humidity/lux) re-renders.

## Project layout

```
home-dashboard/
├── backend/
│   ├── app/                # see app/main.py for the wiring
│   │   ├── api/            # FastAPI routes
│   │   ├── config/         # ConfigV1 schema + loader
│   │   ├── db/             # SQLAlchemy models, repo, session (WAL)
│   │   ├── engine/         # pure decision engine (the core)
│   │   ├── history/        # range queries + downsample
│   │   ├── sensors/        # SensorSource Protocol — Phase 2 swap point
│   │   ├── simulation/     # named scenario builders
│   │   ├── snapshot/       # SnapshotBuilder service
│   │   ├── sun/            # astral wrapper
│   │   └── weather/        # OWM client + DB-cached fetch
│   ├── data/               # config.default.json (rest is gitignored)
│   └── tests/              # pytest, 63 tests
└── frontend/
    └── src/
        ├── api/            # fetch wrapper + SWR hooks + types
        ├── components/     # ZoneGrid, RecommendationsPanel, etc.
        ├── lib/            # urgency / format / time helpers (Vitest tested)
        └── routes/         # Dashboard, Entry, History, Config, Simulate
```
