"""Weather provider dispatcher.

Single entry point for the cache layer. Resolves which backend to call
(Met.no or OpenWeatherMap One Call 3.0) based on ``settings.weather_provider``.

Adding a new provider is two edits: implement ``fetch(...) -> WeatherSnapshot``
in a new module, wire it here. The cache and engine never need to know.
"""
from __future__ import annotations

from app.config.schema import ConfigV1
from app.settings import Settings
from app.weather import client as owm
from app.weather import met_no
from app.weather.schema import WeatherSnapshot


class WeatherProviderError(RuntimeError):
    """Raised when the configured provider can't be reached or auth fails."""


async def fetch(settings: Settings, cfg: ConfigV1) -> WeatherSnapshot:
    """Dispatch to the configured weather provider.

    Default (v0.8+) is Met.no — free, no key, no card on file. Operators
    who already have a working OWM One Call 3.0 subscription can opt back
    in by setting ``weather_provider: owm`` in Add-on options.
    """
    provider = (settings.weather_provider or "met_no").lower()
    lat = cfg.location.latitude
    lon = cfg.location.longitude

    if provider == "met_no":
        return await met_no.fetch(lat, lon, settings.weather_user_agent)
    if provider == "owm":
        return await owm.fetch(settings.owm_api_key, lat, lon)
    raise WeatherProviderError(
        f"Unknown weather_provider {provider!r}. "
        "Expected one of: met_no, owm."
    )
