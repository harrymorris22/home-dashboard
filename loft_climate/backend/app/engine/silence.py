"""Silence explainers — diagnostic strings for actuators where no rule fired.

Why this exists (v0.15): when no rule produces output for a blind group or
window zone, the resulting recommendation has an empty ``reasons`` list.
The dashboard has no material to explain WHY nothing is happening — user
reported the confusion ("if I want airflow, shouldn't it also open the
windows?" on a warm cloudy day where windows correctly stayed closed).

These pure functions read ``Facts`` and produce a single short diagnostic
sentence. The combiner calls them only when the reasons list would
otherwise be empty, and stamps ``silence=True`` on the recommendation so
the frontend can (a) skip the per-zone ↳ line when the diagnostic matches
the top-level headline, and (b) filter silence-origin reasons out of
``pickWhy`` candidates.

Coupling to rule predicates:
- CROSS_VENT_MIN_DELTA_C and INDOOR_WARM_MIN_C are imported from
  ``app.engine.rules`` — same threshold, one source of truth.
- If a rule predicate grows more nuanced than this reflection, the
  matching silence branch reports the raw facts rather than a
  judgement string so drift is impossible.

All strings are capped at ``SILENCE_MAX_CHARS`` (80) so ActionPanel
doesn't wrap unpredictably on a 375px mobile viewport.
"""
from __future__ import annotations

from app.engine.rules import CROSS_VENT_MIN_DELTA_C
from app.engine.types import Facts

SILENCE_MAX_CHARS = 80


def _cap(s: str) -> str:
    """Enforce the 80-char ceiling. Truncate with an ellipsis if over."""
    if len(s) <= SILENCE_MAX_CHARS:
        return s
    return s[: SILENCE_MAX_CHARS - 1].rstrip() + "…"


def explain_silence_blind(group: str, facts: Facts) -> str:
    """Diagnostic: why is no rule firing on this blind group?"""
    if facts.weather is None:
        return _cap("Weather offline — no outside data to decide.")
    if facts.phase in ("night", "pre_dawn"):
        return _cap("Night phase — blinds stay as-is.")
    if not facts.sun_on_sw:
        return _cap("Sun not on glazing — no solar-gain concern.")
    if facts.solar_load in ("moderate", "high"):
        return _cap("Sun on glazing but comfort band met.")
    return _cap("Comfort band met.")


def explain_silence_window(zone: str, facts: Facts) -> str:
    """Diagnostic: why is no rule firing on this window zone?"""
    if facts.weather is None:
        return _cap("Weather offline — no outside data to decide.")
    if not facts.zone_temp:
        # Guards the case where all indoor sensors are offline. Without this,
        # house_avg_temp defaults to 0.0 (classifier.py) and the delta line
        # would fire "outdoor > indoor" for any positive outdoor temp.
        return _cap("Indoor sensors offline — no thermal comparison.")
    if facts.precip:
        return _cap("Rain — windows stay closed.")
    if facts.outdoor is None:
        # Currently unreachable given classifier logic, but the type allows
        # it. Explicit branch beats "safe by luck".
        return _cap("Outdoor category unavailable.")
    if facts.outdoor == "cold_out":
        return _cap("Outdoor cold — opening would chill the loft.")
    if facts.weather.temp_c >= facts.house_avg_temp - CROSS_VENT_MIN_DELTA_C:
        return _cap(
            f"Outdoor {facts.weather.temp_c:.1f}°C ≥ indoor "
            f"{facts.house_avg_temp:.1f}°C — opening would import heat."
        )
    return _cap("Comfort band met, no ventilation trigger.")
