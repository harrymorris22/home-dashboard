import httpx
import pytest
import respx

from app.weather import client as owm
from app.weather.client import OWM30AccessError


SAMPLE_PAYLOAD = {
    "lat": 51.5074,
    "lon": -0.1278,
    "current": {
        "dt": 1721044800,
        "sunrise": 1721014800,
        "sunset": 1721075200,
        "temp": 24.5,
        "feels_like": 25.0,
        "humidity": 55,
        "uvi": 7.2,
        "clouds": 12,
        "wind_speed": 4.5,
        "wind_gust": 6.1,
        "weather": [{"main": "Clear"}],
    },
    "hourly": [
        {
            "dt": 1721044800 + 3600 * i,
            "temp": 24 + i * 0.5,
            "feels_like": 24 + i * 0.5,
            "humidity": 55,
            "clouds": 12,
            "wind_speed": 4.5,
            "uvi": 6.0,
            "pop": 0.0,
        }
        for i in range(6)
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_parses_payload():
    respx.get(owm.OWM_BASE).respond(200, json=SAMPLE_PAYLOAD)
    snap = await owm.fetch("dummy_key", 51.5074, -0.1278)
    assert snap.temp_c == 24.5
    assert snap.uvi == 7.2
    assert snap.conditions == "Clear"
    assert len(snap.hourly) == 6


@pytest.mark.asyncio
@respx.mock
async def test_fetch_401_raises_owm30_access_error():
    respx.get(owm.OWM_BASE).respond(401, json={"cod": 401, "message": "Invalid API key"})
    with pytest.raises(OWM30AccessError):
        await owm.fetch("bad_key", 51.5074, -0.1278)


@pytest.mark.asyncio
async def test_fetch_no_key_raises():
    with pytest.raises(OWM30AccessError):
        await owm.fetch("", 51.5074, -0.1278)
