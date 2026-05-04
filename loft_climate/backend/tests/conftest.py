from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.loader import load_config
from app.config.schema import ConfigV1
from app.db.session import init_db, reset_engine_for_tests
from app.settings import get_settings


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Each test runs against an isolated data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Copy default config into the temp data dir.
    src = Path(__file__).resolve().parent.parent / "data" / "config.default.json"
    dest_default = data_dir / "config.default.json"
    dest_default.write_text(src.read_text())

    s = get_settings()
    monkeypatch.setattr(s, "db_path", data_dir / "climate.db")
    monkeypatch.setattr(s, "config_path", data_dir / "config.json")
    monkeypatch.setattr(s, "config_default_path", dest_default)
    # Tests must never hit the real OWM API. Force degraded mode.
    monkeypatch.setattr(s, "owm_api_key", "")

    reset_engine_for_tests(s.db_path)
    init_db()
    yield


@pytest.fixture
def cfg() -> ConfigV1:
    return load_config()
