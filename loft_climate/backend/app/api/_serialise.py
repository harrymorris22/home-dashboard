"""Helpers to convert engine dataclasses → JSON-friendly dicts."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from app.engine.types import DashboardRecommendation
from app.weather.schema import WeatherSnapshot


def _isoformat(dt: datetime) -> str:
    return dt.isoformat()


def serialise_recommendation(rec: DashboardRecommendation) -> dict:
    return {
        "ts": _isoformat(rec.ts),
        "global": {
            "scenario": rec.global_.scenario,
            "urgency": rec.global_.urgency,
        },
        "by_blind_group": {
            g: {
                "group": b.group,
                "blind_pct": b.blind_pct,
                "urgency": b.urgency,
                "scenario": b.scenario,
                "reasons": b.reasons,
                "silence": b.silence,
            }
            for g, b in rec.by_blind_group.items()
        },
        "by_zone": {
            z: {
                "zone": w.zone,
                "window_open": w.window_open,
                "urgency": w.urgency,
                "scenario": w.scenario,
                "reasons": w.reasons,
                "silence": w.silence,
            }
            for z, w in rec.by_zone.items()
        },
        "prompts": rec.prompts,
        "rule_errors": rec.rule_errors,
    }


def serialise_weather(weather: WeatherSnapshot | None) -> dict | None:
    if weather is None:
        return None
    return {
        "fetched_at": _isoformat(weather.fetched_at),
        "stale": weather.stale,
        "temp_c": weather.temp_c,
        "feels_like_c": weather.feels_like_c,
        "humidity_pct": weather.humidity_pct,
        "cloud_cover_pct": weather.cloud_cover_pct,
        "wind_speed_mps": weather.wind_speed_mps,
        "wind_gust_mps": weather.wind_gust_mps,
        "uvi": weather.uvi,
        "conditions": weather.conditions,
        "precip_now": weather.precip_now,
        "sunrise": _isoformat(weather.sunrise),
        "sunset": _isoformat(weather.sunset),
    }
