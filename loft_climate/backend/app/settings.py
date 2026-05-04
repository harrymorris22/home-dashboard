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

    owm_api_key: str = Field(default="")
    latitude: float = 51.5074
    longitude: float = -0.1278
    timezone: str = "Europe/London"

    db_path: Path = DATA_DIR / "climate.db"
    config_path: Path = DATA_DIR / "config.json"
    config_default_path: Path = DATA_DIR / "config.default.json"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Home Assistant integration. ha_base_url + ha_token enable the WS sensor source.
    # ha_entity_map is JSON in env (pydantic-settings parses it):
    #   {"bedroom": {"temp": "sensor.aqara_bedroom_temperature",
    #                "humidity": "sensor.aqara_bedroom_humidity"}}
    ha_base_url: str = ""
    ha_token: str = ""
    ha_entity_map: dict[str, dict[str, str]] = Field(default_factory=dict)
    # Outdoor microclimate sensor mapping (e.g. SwitchBot meter on the building).
    # Empty means: keep using OWM forecast values.
    ha_outdoor_entities: dict[str, str] = Field(default_factory=dict)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
