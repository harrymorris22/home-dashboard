"""Pytest fixtures — isolate each test in its own SQLite + settings."""
from __future__ import annotations

import pytest

from app.db.session import init_db, reset_engine_for_tests
from app.settings import get_settings


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    s = get_settings()
    monkeypatch.setattr(s, "db_path", data_dir / "desk.db")
    # Tests should never reach real services unless explicitly mocked.
    monkeypatch.setattr(s, "loft_internal_url", "http://test-loft-climate:8000")
    monkeypatch.setattr(s, "ical_url", "")
    reset_engine_for_tests(s.db_path)
    init_db()
    # Reset module-level caches between tests so cache state doesn't leak.
    from app.widgets import climate as climate_mod
    from app.widgets import stock as stock_mod
    from app.widgets import calendar as calendar_mod
    climate_mod._cache["fetched_at"] = None
    climate_mod._cache["payload"] = None
    climate_mod._cache["stale"] = False
    stock_mod._cache.clear()
    calendar_mod._cache["fetched_at"] = None
    calendar_mod._cache["payload"] = None
    yield
