# home-dashboard

Smart climate control for a SW-facing London loft. Built around a Home Assistant
Add-on so it runs on the same Pi as HA and uses the same Zigbee/BLE sensors.

This repository is **also a custom Home Assistant Add-on repository**. To install
the dashboard on your HA instance:

1. **Settings → Add-ons → Add-on Store**
2. Click the **⋮** menu → **Repositories** → paste this repo URL → **Add**
3. Find **Loft Climate Dashboard** in the store, click **Install**, then **Start**.

The Add-on lives in [`loft_climate/`](./loft_climate/), with full docs in
[`loft_climate/DOCS.md`](./loft_climate/DOCS.md).

## Project layout

```
home-dashboard/
├── repository.yaml              # HA Add-on repository metadata
├── loft_climate/                # the Add-on
│   ├── config.yaml              #   Add-on manifest (HA reads this)
│   ├── Dockerfile               #   multi-stage build (node + python)
│   ├── run.sh                   #   container entrypoint
│   ├── DOCS.md                  #   shown in HA Add-on UI
│   ├── README.md                #   project narrative
│   ├── ARCHITECTURE.md          #   Phase 2 migration notes
│   ├── TODOS.md                 #   deferred work
│   ├── backend/                 #   FastAPI + SQLite + decision engine
│   └── frontend/                #   React + Vite + Tailwind
└── .gitignore
```

## Local development (Mac)

```bash
# backend
cd loft_climate/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# frontend (in another terminal)
cd loft_climate/frontend
npm install
npm run dev
```

Dashboard at <http://127.0.0.1:5173>. Vite proxies `/api/*` to the backend.

## Production (HA Add-on)

The same code, packaged as a Docker container that HA builds and runs. The
Add-on serves the built frontend + the API at the same origin (port 8000), so
no CORS, no proxy, no Vite. Install via the steps at the top of this README.
