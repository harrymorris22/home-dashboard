"""Coverage for the Met.no adapter."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.weather import met_no
from app.weather.met_no import (
    MetNoError,
    _conditions_from_symbol,
    _effective_uvi,
)


# A trimmed but realistic Met.no LocationForecast 2.0 complete response.
SAMPLE_PAYLOAD = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-0.13, 51.51, 11.0]},
    "properties": {
        "meta": {
            "updated_at": "2026-05-27T08:00:00Z",
            "units": {
                "air_temperature": "celsius",
                "wind_speed": "m/s",
                "cloud_area_fraction": "%",
                "relative_humidity": "%",
                "precipitation_amount": "mm",
                "probability_of_precipitation": "%",
                "ultraviolet_index_clear_sky": "1",
            },
        },
        "timeseries": [
            {
                "time": "2026-05-27T08:00:00Z",
                "data": {
                    "instant": {
                        "details": {
                            "air_temperature": 18.5,
                            "cloud_area_fraction": 75.0,
                            "relative_humidity": 65.0,
                            "wind_speed": 3.5,
                            "wind_speed_of_gust": 6.2,
                            "ultraviolet_index_clear_sky": 4.0,
                        }
                    },
                    "next_1_hours": {
                        "summary": {"symbol_code": "cloudy"},
                        "details": {
                            "precipitation_amount": 0.0,
                            "probability_of_precipitation": 15.0,
                        },
                    },
                },
            },
            {
                "time": "2026-05-27T09:00:00Z",
                "data": {
                    "instant": {
                        "details": {
                            "air_temperature": 19.0,
                            "cloud_area_fraction": 50.0,
                            "relative_humidity": 60.0,
                            "wind_speed": 3.0,
                            "ultraviolet_index_clear_sky": 5.0,
                        }
                    },
                    "next_1_hours": {
                        "summary": {"symbol_code": "partlycloudy_day"},
                        "details": {
                            "precipitation_amount": 0.0,
                            "probability_of_precipitation": 5.0,
                        },
                    },
                },
            },
        ],
    },
}


# --- Symbol → conditions mapping ------------------------------------------


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("clearsky_day", "Clear"),
        ("fair_night", "Clear"),
        ("partlycloudy_day", "Clouds"),
        ("cloudy", "Clouds"),
        ("rain", "Rain"),
        ("lightrain", "Rain"),
        ("heavyrainshowers_day", "Rain"),
        ("snow", "Snow"),
        ("lightsleet", "Snow"),
        ("rainshowersandthunder_day", "Thunderstorm"),
        ("snowandthunder", "Thunderstorm"),
        ("fog", "Fog"),
        (None, "Unknown"),
        ("", "Unknown"),
    ],
)
def test_conditions_from_symbol(symbol, expected):
    assert _conditions_from_symbol(symbol) == expected


# --- UV attenuation -------------------------------------------------------


def test_effective_uvi_full_sun():
    assert _effective_uvi(5.0, 0.0) == 5.0


def test_effective_uvi_full_overcast():
    # Clouds attenuate 80% of clear-sky UV → 20% remaining.
    result = _effective_uvi(5.0, 100.0)
    assert abs(result - 1.0) < 0.001


def test_effective_uvi_partial_cloud():
    # 50% cloud cover → 40% attenuation → 60% remaining of 5.0 = 3.0
    result = _effective_uvi(5.0, 50.0)
    assert abs(result - 3.0) < 0.001


# --- _parse end-to-end ----------------------------------------------------


def test_parse_extracts_current_conditions():
    snap = met_no._parse(SAMPLE_PAYLOAD, lat=51.5074, lon=-0.1278)
    assert snap.temp_c == 18.5
    assert snap.cloud_cover_pct == 75.0
    assert snap.humidity_pct == 65.0
    assert snap.wind_speed_mps == 3.5
    assert snap.wind_gust_mps == 6.2
    assert snap.conditions == "Clouds"
    assert snap.precip_now is False
    # UV at 75% cloud: 4.0 * (1 - 0.8 * 0.75) = 4.0 * 0.4 = 1.6
    assert abs(snap.uvi - 1.6) < 0.01


def test_parse_populates_hourly():
    snap = met_no._parse(SAMPLE_PAYLOAD, lat=51.5074, lon=-0.1278)
    assert len(snap.hourly) == 2
    # pop reported as 15% by Met.no, stored as 0.15.
    assert abs(snap.hourly[0].pop - 0.15) < 0.001
    assert snap.hourly[0].temp_c == 18.5
    assert snap.hourly[1].temp_c == 19.0


def test_parse_handles_precipitation_now():
    """precip_now is True when the next-hour forecast has precipitation_amount > 0."""
    payload = dict(SAMPLE_PAYLOAD)
    payload["properties"] = dict(payload["properties"])
    ts0 = dict(payload["properties"]["timeseries"][0])
    ts0["data"] = dict(ts0["data"])
    ts0["data"]["next_1_hours"] = {
        "summary": {"symbol_code": "rain"},
        "details": {"precipitation_amount": 1.2, "probability_of_precipitation": 90.0},
    }
    payload["properties"]["timeseries"] = [ts0] + list(payload["properties"]["timeseries"][1:])

    snap = met_no._parse(payload, lat=51.5074, lon=-0.1278)
    assert snap.precip_now is True
    assert snap.conditions == "Rain"


def test_parse_empty_timeseries_raises():
    bad = {"properties": {"timeseries": []}}
    with pytest.raises(MetNoError):
        met_no._parse(bad, lat=51.5074, lon=-0.1278)


def test_parse_computes_sunrise_sunset_from_astral():
    """sunrise/sunset are computed locally, not pulled from the API."""
    snap = met_no._parse(SAMPLE_PAYLOAD, lat=51.5074, lon=-0.1278)
    assert snap.sunrise is not None
    assert snap.sunset is not None
    # Sunrise must be before sunset on the same day.
    assert snap.sunrise < snap.sunset


# --- HTTP layer ----------------------------------------------------------


@respx.mock
async def test_fetch_requires_email_in_user_agent():
    with pytest.raises(MetNoError) as exc:
        await met_no.fetch(lat=51.5, lon=-0.1, user_agent="no-email-here")
    assert "contact email" in str(exc.value).lower()


@respx.mock
async def test_fetch_403_raises_with_helpful_message():
    respx.get(met_no.MET_NO_BASE).mock(return_value=httpx.Response(403, json={}))
    with pytest.raises(MetNoError) as exc:
        await met_no.fetch(
            lat=51.5, lon=-0.1, user_agent="loft-climate/0.8 ops@example.com"
        )
    assert "User-Agent" in str(exc.value)


@respx.mock
async def test_fetch_happy_path_returns_snapshot():
    respx.get(met_no.MET_NO_BASE).mock(
        return_value=httpx.Response(200, json=SAMPLE_PAYLOAD)
    )
    snap = await met_no.fetch(
        lat=51.5074, lon=-0.1278, user_agent="loft-climate/0.8 ops@example.com"
    )
    assert snap.temp_c == 18.5
    assert snap.conditions == "Clouds"
    assert snap.stale is False


@respx.mock
async def test_fetch_passes_polite_user_agent_header():
    """Met.no's abuse policy requires identifying UA. Verify we send it."""
    route = respx.get(met_no.MET_NO_BASE).mock(
        return_value=httpx.Response(200, json=SAMPLE_PAYLOAD)
    )
    await met_no.fetch(
        lat=51.5, lon=-0.1, user_agent="loft-climate/0.8 ops@example.com"
    )
    assert route.called
    sent = route.calls.last.request.headers["user-agent"]
    assert sent == "loft-climate/0.8 ops@example.com"
