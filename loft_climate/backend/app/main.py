from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_blinds,
    routes_config,
    routes_ha,
    routes_history,
    routes_outdoor,
    routes_push,
    routes_state,
    routes_weather,
    routes_windows,
)
from app.db.session import init_db
from app.push.scheduler import PushScheduler
from app.push.vapid import VapidLoadError, load_or_create
from app.sensors.homeassistant import HAClient
from app.settings import BACKEND_DIR, get_settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    ha_client: HAClient | None = None
    if settings.ha_base_url and settings.ha_token:
        ha_client = HAClient(settings.ha_base_url, settings.ha_token)
        await ha_client.start()
        log.info("HA WS client started against %s", settings.ha_base_url)
    app.state.ha_client = ha_client

    # VAPID — load or create on miss; on parse failure, halt push subsystem
    # but keep the rest of the app running so the user can recover from the UI.
    app.state.vapid_keys = None
    try:
        app.state.vapid_keys = load_or_create(settings.vapid_keys_path, settings.vapid_subject)
        log.info("[push] VAPID keys ready (%s)", settings.vapid_keys_path)
    except VapidLoadError:
        log.error(
            "[push] VAPID file unreadable; push subsystem disabled until manual regenerate"
        )

    push_scheduler: PushScheduler | None = None
    if app.state.vapid_keys is not None:
        push_scheduler = PushScheduler(
            ha_client=ha_client,
            vapid_provider=lambda: app.state.vapid_keys,
        )
        await push_scheduler.start()
    app.state.push_scheduler = push_scheduler

    try:
        yield
    finally:
        if push_scheduler is not None:
            await push_scheduler.stop()
        if ha_client is not None:
            await ha_client.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Home Dashboard",
        description="Smart climate control for a SW-facing London loft",
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
    app.include_router(routes_state.router)
    app.include_router(routes_history.router)
    app.include_router(routes_config.router)
    app.include_router(routes_weather.router)
    app.include_router(routes_outdoor.router)
    app.include_router(routes_ha.router)
    app.include_router(routes_push.router)
    app.include_router(routes_blinds.router)
    app.include_router(routes_windows.router)

    @app.get("/healthz")
    def healthz():
        return {
            "ok": True,
            "ha_connected": (
                getattr(app.state, "ha_client", None) is not None
                and app.state.ha_client.connected
            ),
        }

    # Serve the built frontend if FRONTEND_DIST points at a directory containing
    # index.html. In dev (Mac), Vite serves the frontend separately and proxies
    # /api → :8000, so this mount is skipped. In prod (HA Add-on), the Dockerfile
    # builds the frontend and sets FRONTEND_DIST=/app/frontend/dist.
    dist_path = Path(
        os.environ.get("FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist"))
    )
    if (dist_path / "index.html").is_file():
        assets = dist_path / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str, request: Request):
            # API routes registered above match first. This catch-all is for the
            # SPA: serve a real file if it exists, otherwise fall back to
            # index.html so React Router handles client-side routing.
            candidate = dist_path / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_path / "index.html")

    return app


app = create_app()
