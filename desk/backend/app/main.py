"""Desk Dashboard backend entrypoint.

FastAPI app with widget routers and a single background MonitorTask.
Mirrors loft_climate's lifespan + CORS + SPA-fallback shape, stripped of
HA/push/VAPID concerns. See Phase 3 plan for the full architecture.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.session import init_db
from app.monitor import MonitorTask
from app.settings import BACKEND_DIR, get_settings
from app.widgets import calendar as calendar_routes
from app.widgets import climate as climate_routes
from app.widgets import stock as stock_routes
from app.widgets import system as system_routes

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()

    monitor = MonitorTask(
        targets=list(settings.ping_targets),
        interval_s=settings.ping_interval_s,
        retention_days=settings.uptime_retention_days,
    )
    await monitor.start()
    app.state.monitor = monitor
    log.info("[desk] startup complete")

    try:
        yield
    finally:
        await monitor.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Desk Dashboard",
        description="Multi-widget desk dashboard for iPad",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(climate_routes.router)
    app.include_router(stock_routes.router)
    app.include_router(calendar_routes.router)
    app.include_router(system_routes.router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # Serve built frontend if FRONTEND_DIST points at a dir with index.html.
    # In dev (Vite), this branch is skipped and Vite proxies /api → :8001.
    dist_path = Path(
        os.environ.get("FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist"))
    )
    if (dist_path / "index.html").is_file():
        assets = dist_path / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str, request: Request):
            candidate = dist_path / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_path / "index.html")

    return app


app = create_app()
