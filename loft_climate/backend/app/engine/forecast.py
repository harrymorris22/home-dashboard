"""Project the engine forward across the next N hours and detect the next action.

Indoor sensor readings are assumed constant — Phase 1 doesn't model thermal mass.
Weather, sun position, time-of-day phase, and forecast-max all advance. Each step
runs `decide()` against a synthetic future Snapshot; transitions surface when an
actuator's recommended value changes compared to the previous step.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone

from app.engine.engine import decide
from app.engine.rules import Rule
from app.engine.types import Snapshot
from app.sun import calculator as suncalc
from app.weather.schema import WeatherSnapshot


def _future_weather(base: WeatherSnapshot, hour_index: int) -> WeatherSnapshot:
    h = base.hourly[hour_index]
    forward_hourly = base.hourly[hour_index:]
    return WeatherSnapshot(
        fetched_at=h.ts,
        temp_c=h.temp_c,
        feels_like_c=h.feels_like_c,
        humidity_pct=h.humidity_pct,
        cloud_cover_pct=h.cloud_cover_pct,
        wind_speed_mps=h.wind_speed_mps,
        wind_gust_mps=None,
        uvi=h.uvi,
        conditions=base.conditions,
        precip_now=h.pop >= 0.5,
        sunrise=base.sunrise,
        sunset=base.sunset,
        hourly=forward_hourly,
        stale=False,
    )


def project_actions(
    base_snap: Snapshot,
    horizon_hours: int = 12,
    rules: list[Rule] | None = None,
    max_transitions: int = 8,
) -> list[dict]:
    """Return upcoming actuator transitions, ordered by time.

    Each transition: ``{ts, actuator, from, to, scenario, reasoning}``.
    """
    if base_snap.weather is None or not base_snap.weather.hourly:
        return []

    base_rec = decide(base_snap, rules=rules)
    last_blind: dict[str, int] = {
        g: r.blind_pct for g, r in base_rec.by_blind_group.items() if r.scenario != "neutral"
    }
    last_window: dict[str, bool] = {
        z: r.window_open
        for z, r in base_rec.by_zone.items()
        if r.window_open is not None
    }

    transitions: list[dict] = []
    h_count = min(horizon_hours, len(base_snap.weather.hourly))
    for h in range(h_count):
        future_ts = base_snap.weather.hourly[h].ts
        # Met.no's hourly forecast starts at the top of the current hour.
        # If we're 40 minutes into the 11:00 hour, hourly[0].ts is 11:00
        # UTC — already past. Skip past entries: they display as "11:00
        # now" in the UI (formatDelta returns "now" for negative deltas)
        # AND they leak stale forecast values into reasoning that
        # contradict the live outdoor-sensor override applied to
        # base_snap.weather.temp_c. Current-hour recommendations already
        # live in base_rec, which uses the overridden weather — no need
        # to project them again from a possibly-stale Met.no forecast.
        if future_ts <= base_snap.now:
            continue
        future_weather = _future_weather(base_snap.weather, h)
        future_sun = suncalc.compute(future_ts, base_snap.config)
        future_snap = replace(base_snap, now=future_ts, weather=future_weather, sun=future_sun)
        rec = decide(future_snap, rules=rules)

        for g, br in rec.by_blind_group.items():
            if br.scenario == "neutral":
                continue
            prior = last_blind.get(g)
            if prior is None or br.blind_pct != prior:
                transitions.append(
                    {
                        "ts": future_ts.isoformat(),
                        "actuator": f"blind:{g}",
                        "from": prior,
                        "to": br.blind_pct,
                        "scenario": br.scenario,
                        "reasoning": br.reasons[0] if br.reasons else "",
                    }
                )
                last_blind[g] = br.blind_pct

        for z, wr in rec.by_zone.items():
            if wr.window_open is None:
                continue
            prior = last_window.get(z)
            if prior is None or wr.window_open != prior:
                transitions.append(
                    {
                        "ts": future_ts.isoformat(),
                        "actuator": f"window:{z}",
                        "from": None if prior is None else ("open" if prior else "closed"),
                        "to": "open" if wr.window_open else "closed",
                        "scenario": wr.scenario,
                        "reasoning": wr.reasons[0] if wr.reasons else "",
                    }
                )
                last_window[z] = wr.window_open

        if len(transitions) >= max_transitions:
            break

    return transitions[:max_transitions]
