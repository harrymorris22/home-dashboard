# Desk Dashboard

Multi-widget desk dashboard for iPad. Runs as an HA Add-on alongside the
Loft Climate Add-on.

See [DOCS.md](./DOCS.md) for configuration and architecture notes.

## Dev

```bash
# Backend (port 8001)
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
uvicorn app.main:app --port 8001 --reload

# Frontend (port 5174, proxies /api → :8001)
cd frontend && npm install && npm run dev

# Tests
cd backend && pytest -q
cd frontend && npm test
```

## Shared frontend primitives

`src/_shared/*` is synced from `packages/ui/src/*` via `bash scripts/sync-shared.sh` at the repo root. **Do not edit `_shared/` directly.**

## v0.1.0 scope

4 widgets, no push notifications, no layout customisation. See [the plan](../../.claude/plans/project-smart-climate-tender-gizmo.md) for full architecture + deferred TODOs.
