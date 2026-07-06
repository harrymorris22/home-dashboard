"""All decision rules for Phase 1.

Each rule is a plain dataclass — no decorator side effects. The exported
ALL_RULES list is the single source of truth; engine.decide() takes it as
a parameter so tests can pass a subset deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.engine.types import (
    BLIND_GROUPS,
    Facts,
    RuleOutput,
    Urgency,
    WINDOW_ZONES,
)


# v0.15: shared with app.engine.silence. Any tuning of these thresholds must
# happen HERE — silence explainers import them so diagnostic strings stay
# consistent with the rules they explain. Duplicating the number in a
# silence helper let the two drift silently (CEO + Eng review flagged this).
CROSS_VENT_MIN_DELTA_C = 1.5  # outdoor must be this many °C below indoor for cross-vent
INDOOR_WARM_MIN_C = 22.5  # house avg above this triggers "warm indoor" branch


@dataclass(frozen=True)
class Rule:
    name: str
    priority: int
    predicate: Callable[[Facts], bool]
    produce: Callable[[Facts], RuleOutput]


def _all_blinds_down() -> dict[str, int]:
    return {g: 100 for g in BLIND_GROUPS}


def _all_blinds_up() -> dict[str, int]:
    return {g: 0 for g in BLIND_GROUPS}


def _all_windows(open_: bool) -> dict[str, bool]:
    return {z: open_ for z in WINDOW_ZONES}


# ---------------------------------------------------------------------------
# House-wide blind rules (priority 80)
# ---------------------------------------------------------------------------


def _block_solar_gain_pred(f: Facts) -> bool:
    return (
        f.weather is not None
        and (f.outdoor == "hot_out" or (f.forecast_max_c is not None and f.forecast_max_c >= 22))
        and f.sun_on_sw
        and f.sky in ("sunny", "partly")
    )


def _block_solar_gain(f: Facts) -> RuleOutput:
    fm = f.forecast_max_c if f.forecast_max_c is not None else (f.weather.temp_c if f.weather else 0)
    return RuleOutput(
        rule="block_solar_gain",
        priority=80,
        blind_targets=_all_blinds_down(),
        urgency="amber",
        scenario="hot_sunny",
        reasoning=f"Forecast max {fm:.0f}°C with sun on SW glazing — close blinds.",
    )


def _harvest_solar_pred(f: Facts) -> bool:
    if f.weather is None or not f.sun_on_sw:
        return False
    if f.outdoor != "cold_out":
        return False
    indoor_cold = any(label == "cold" for label in f.zone_thermal.values())
    return indoor_cold and f.sky in ("sunny", "partly")


def _harvest_solar(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="harvest_solar",
        priority=80,
        blind_targets=_all_blinds_up(),
        urgency="green",
        scenario="cold_sunny",
        reasoning="Cold outside, sun on SW — open blinds to harvest solar gain.",
    )


def _let_light_in_pred(f: Facts) -> bool:
    """Daytime + no solar gain risk → blinds up for natural light and airflow.

    Skipped when:
      - dark (pre_dawn / post_sunset / night) — `release_blinds` and others own those
      - cold outside — `insulate_blinds` wins (blinds down for thermal envelope)
      - actively in a solar-gain situation (sun on SW, sunny sky, AND hot/forecast hot)
        — `block_solar_gain` will fire at the same priority and produce the right answer

    In every other daytime case (cloudy, sun off SW, mild day) blinds go up.
    """
    if f.weather is None:
        return False
    if f.phase in ("pre_dawn", "post_sunset", "night"):
        return False
    if f.outdoor == "cold_out":
        return False
    # Active solar-gain situation? Defer to block_solar_gain (same priority).
    # Skip predicate must exactly match block_solar_gain's predicate so we never
    # both fire at the same priority with opposite targets.
    if f.sun_on_sw and f.sky in ("sunny", "partly"):
        forecast_hot = f.forecast_max_c is not None and f.forecast_max_c >= 22
        if f.outdoor == "hot_out" or forecast_hot:
            return False
    return True


def _let_light_in(f: Facts) -> RuleOutput:
    cause = "cloudy" if f.sky == "cloudy" else (
        "sun off the SW face" if not f.sun_on_sw else "mild day"
    )
    return RuleOutput(
        rule="let_light_in",
        priority=80,
        blind_targets=_all_blinds_up(),
        urgency="green",
        scenario="daytime_light",
        # v0.14: dropped "and airflow" from the reasoning. This rule only
        # sets blind_targets; it doesn't open windows. Airflow requires
        # _cross_ventilate to also fire (which needs outdoor cooler than
        # indoor by ≥1.5°C). When both fire the user sees both. When only
        # this fires, promising airflow was a lie.
        reasoning=f"{cause.capitalize()} — no solar gain to block. Blinds up for natural light.",
    )


def _insulate_blinds_pred(f: Facts) -> bool:
    if f.weather is None:
        return False
    return f.outdoor == "cold_out" and not f.sun_on_sw


def _insulate_blinds(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="insulate_blinds",
        priority=80,
        blind_targets=_all_blinds_down(),
        urgency="green",
        scenario="cold_no_sun",
        reasoning="Cold outside, no sun — blinds down for insulation.",
    )


# ---------------------------------------------------------------------------
# House-wide window rules (priority 80)
# ---------------------------------------------------------------------------


def _cross_ventilate_pred(f: Facts) -> bool:
    """Open windows when indoor is warm AND outdoor is meaningfully cooler.

    Fires regardless of outdoor classification (mild OR hot) — the physics is
    "indoor > outdoor by enough", not "outdoor exceeds some absolute threshold".
    Skipped when outdoor is cold_out (would chill the loft) or it's raining.
    Wind helps but isn't required: stack-effect ventilates a two-storey loft
    even on still days when the temp gradient is large.
    """
    if f.weather is None or f.precip:
        return False
    if f.outdoor == "cold_out":
        return False
    if not f.zone_temp:
        return False
    indoor_avg = f.house_avg_temp
    indoor_warm = (
        any(label == "hot" for label in f.zone_thermal.values())
        or indoor_avg > INDOOR_WARM_MIN_C
    )
    if not indoor_warm:
        return False
    return f.weather.temp_c < indoor_avg - CROSS_VENT_MIN_DELTA_C


def _cross_ventilate(f: Facts) -> RuleOutput:
    assert f.weather is not None
    delta = f.house_avg_temp - f.weather.temp_c
    wind = f.weather.wind_speed_mps
    wind_phrase = (
        f"{wind:.1f} m/s breeze" if wind >= 1.5 else "still air; rely on stack effect"
    )
    return RuleOutput(
        rule="cross_ventilate",
        priority=80,
        window_targets=_all_windows(True),
        urgency="amber",
        scenario="vent_to_cool",
        reasoning=(
            f"Indoor {f.house_avg_temp:.1f}°C, outdoor {f.weather.temp_c:.1f}°C "
            f"({delta:.1f}°C cooler) — {wind_phrase}, open to vent heat."
        ),
    )


def _seal_against_heat_pred(f: Facts) -> bool:
    if f.weather is None:
        return False
    if f.outdoor != "hot_out":
        return False
    # Still air OR outdoor hotter than indoor.
    if f.wind == "still":
        return True
    if f.zone_temp:
        return f.weather.temp_c >= f.house_avg_temp
    return False


def _seal_against_heat(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="seal_against_heat",
        priority=80,
        window_targets=_all_windows(False),
        urgency="amber",
        scenario="hot_still",
        reasoning=f"Outdoor {f.weather.temp_c:.1f}°C, still air — keep windows closed to trap cool.",
    )


def _seal_for_warmth_pred(f: Facts) -> bool:
    if f.weather is None:
        return False
    return f.outdoor == "cold_out"


def _seal_for_warmth(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="seal_for_warmth",
        priority=80,
        window_targets=_all_windows(False),
        urgency="green",
        scenario="cold",
        reasoning="Cold outside — windows closed to retain heat.",
    )


# ---------------------------------------------------------------------------
# Time-bounded rules (priority 70)
# ---------------------------------------------------------------------------


def _night_purge_pred(f: Facts) -> bool:
    if f.weather is None or f.precip:
        return False
    if f.phase not in ("post_sunset", "evening", "night"):
        return False
    if not f.zone_temp:
        return False
    indoor_hot = any(t > 24 for t in f.zone_temp.values())
    return indoor_hot and f.weather.temp_c < f.house_avg_temp - 2


def _night_purge(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="night_purge",
        priority=70,
        window_targets=_all_windows(True),
        urgency="amber",
        scenario="post_sunset_purge",
        reasoning=f"Indoor warmer than {f.weather.temp_c:.1f}°C outdoor — purge heat.",
    )


def _release_blinds_pred(f: Facts) -> bool:
    if f.weather is None:
        return False
    if f.phase not in ("post_sunset", "evening", "night"):
        return False
    if f.sun_on_sw:
        return False
    return any(t > 24 for t in f.zone_temp.values())


def _release_blinds(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="release_blinds",
        priority=70,
        blind_targets=_all_blinds_up(),
        urgency="green",
        scenario="post_sunset_release",
        reasoning="Post-sunset, indoor warm — blinds up so heat can radiate out.",
    )


def _pre_cool_pred(f: Facts) -> bool:
    if f.weather is None or f.precip:
        return False
    if f.phase != "pre_dawn":
        return False
    if f.forecast_max_c is None or f.forecast_max_c < 26:
        return False
    return f.weather.temp_c < 18


def _pre_cool(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="pre_cool",
        priority=70,
        window_targets=_all_windows(True),
        urgency="amber",
        scenario="pre_dawn_pre_cool",
        reasoning=f"Pre-dawn {f.weather.temp_c:.1f}°C, hot day forecast ({f.forecast_max_c:.0f}°C) — pre-cool.",
    )


# ---------------------------------------------------------------------------
# Zone-specific rules (priority 90+)
# ---------------------------------------------------------------------------


def _bedtime_prep_pred(f: Facts) -> bool:
    if not f.bedtime_window:
        return False
    bedroom_t = f.zone_apparent.get("bedroom")
    if bedroom_t is None:
        return False
    bedroom_cfg = f.config.zones.get("bedroom")
    if bedroom_cfg is None or bedroom_cfg.bedtime_target_c is None:
        return False
    return bedroom_t > bedroom_cfg.bedtime_target_c


def _bedtime_prep(f: Facts) -> RuleOutput:
    bedroom_t = f.zone_apparent.get("bedroom", 0.0)
    target = f.config.zones["bedroom"].bedtime_target_c or 21.0
    # Close blinds to stop residual gain; window state depends on outdoor.
    window_open = bool(
        f.weather is not None and f.weather.temp_c < bedroom_t - 1.0 and not f.precip
    )
    return RuleOutput(
        rule="bedtime_prep",
        priority=90,
        blind_targets={"bedroom": 100},
        window_targets={"bedroom": window_open},
        urgency="amber",
        scenario="bedtime_prep",
        reasoning=f"Bedroom {bedroom_t:.1f}°C > target {target:.0f}°C, bedtime soon.",
    )


def _bedroom_too_hot_safety_pred(f: Facts) -> bool:
    bedroom_t = f.zone_apparent.get("bedroom")
    if bedroom_t is None:
        return False
    if not f.bedtime_window and f.phase not in ("evening", "night", "post_sunset"):
        return False
    return bedroom_t >= 25.0


def _bedroom_too_hot_safety(f: Facts) -> RuleOutput:
    bedroom_t = f.zone_apparent.get("bedroom", 0.0)
    # If outdoor is cooler, force bedroom window open.
    window_open = bool(
        f.weather is not None and f.weather.temp_c < bedroom_t - 0.5 and not f.precip
    )
    return RuleOutput(
        rule="bedroom_too_hot_safety",
        priority=100,
        blind_targets={"bedroom": 0},
        window_targets={"bedroom": window_open},
        urgency="red",
        scenario="bedroom_overheat",
        reasoning=f"Bedroom {bedroom_t:.1f}°C — too hot to sleep. Open everything that helps.",
    )


def _apex_stack_vent_pred(f: Facts) -> bool:
    if f.weather is None or f.precip:
        return False
    apex_cfg = f.config.zones.get("ceiling_apex")
    if apex_cfg is None or apex_cfg.stack_vent_delta_c is None:
        return False
    if "ceiling_apex" not in f.zone_temp:
        return False
    apex_t = f.zone_temp["ceiling_apex"]
    return f.apex_excess_c >= apex_cfg.stack_vent_delta_c and f.weather.temp_c < apex_t - 1.0


def _apex_stack_vent(f: Facts) -> RuleOutput:
    apex_t = f.zone_temp.get("ceiling_apex", 0.0)
    return RuleOutput(
        rule="apex_stack_vent",
        priority=75,
        window_targets={"mezzanine": True, "ceiling_apex": True},
        urgency="amber",
        scenario="apex_stratification",
        reasoning=f"Apex {apex_t:.1f}°C, {f.apex_excess_c:.1f}°C above house avg — vent the stack.",
    )


# ---------------------------------------------------------------------------
# Override rules (priority 110)
# ---------------------------------------------------------------------------


def _rain_suppress_pred(f: Facts) -> bool:
    return f.precip


def _rain_suppress(f: Facts) -> RuleOutput:
    return RuleOutput(
        rule="rain_suppress",
        priority=110,
        window_targets=_all_windows(False),
        urgency="amber",
        scenario="rain_override",
        reasoning="Rain/storm — windows closed regardless of other rules.",
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


ALL_RULES: list[Rule] = [
    Rule("block_solar_gain", 80, _block_solar_gain_pred, _block_solar_gain),
    Rule("harvest_solar", 80, _harvest_solar_pred, _harvest_solar),
    Rule("let_light_in", 80, _let_light_in_pred, _let_light_in),
    Rule("insulate_blinds", 80, _insulate_blinds_pred, _insulate_blinds),
    Rule("cross_ventilate", 80, _cross_ventilate_pred, _cross_ventilate),
    Rule("seal_against_heat", 80, _seal_against_heat_pred, _seal_against_heat),
    Rule("seal_for_warmth", 80, _seal_for_warmth_pred, _seal_for_warmth),
    Rule("night_purge", 70, _night_purge_pred, _night_purge),
    Rule("release_blinds", 70, _release_blinds_pred, _release_blinds),
    Rule("pre_cool", 70, _pre_cool_pred, _pre_cool),
    Rule("apex_stack_vent", 75, _apex_stack_vent_pred, _apex_stack_vent),
    Rule("bedtime_prep", 90, _bedtime_prep_pred, _bedtime_prep),
    Rule("bedroom_too_hot_safety", 100, _bedroom_too_hot_safety_pred, _bedroom_too_hot_safety),
    Rule("rain_suppress", 110, _rain_suppress_pred, _rain_suppress),
]
