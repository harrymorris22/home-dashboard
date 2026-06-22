"""Runtime settings for the desk dashboard backend.

Populated from env vars (set by run.sh from the HA Add-on options.json) plus
a small set of derived defaults. Single source of truth — every widget +
the MonitorTask read from get_settings()."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Climate widget — calls the loft_climate Add-on via HA Supervisor's
    # per-Add-on local DNS. `local_loft_climate` resolves to the climate
    # container; reachable plain-HTTP on whatever port that Add-on exposes
    # (8000 in our case).
    loft_internal_url: str = "http://local_loft_climate:8000"

    # Calendar widget — iCloud or Google iCal share link (read-only).
    # Stored as a "password" type in config.yaml so HA UI masks it.
    ical_url: str = ""

    # Oura widget — Personal Access Token from cloud.ouraring.com.
    # Stored as a "password" type in config.yaml so HA UI masks it.
    oura_pat_token: str = ""

    # System widget — internet uptime probe targets. Gateway gets appended
    # at runtime if discoverable.
    ping_targets: list[str] = Field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])
    ping_interval_s: int = 30
    uptime_retention_days: int = 7

    # Stock widget — default ticker plus market hours. LSE: 08:00–16:30 UK.
    default_stock_ticker: str = "LQQ3.L"

    # CORS / dev.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    db_path: Path = DATA_DIR / "desk.db"
    log_level: str = "info"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
