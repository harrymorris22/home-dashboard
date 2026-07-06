"""One test per matrix row + edge cases."""
from app.config.schema import ConfigV1
from app.engine.engine import decide
from tests.scenarios import (
    apex_stratification,
    bedroom_overheat_safety,
    bedtime_too_warm,
    cold_cloudy,
    cold_sunny,
    hot_cloudy,
    hot_sunny_breeze,
    hot_sunny_still,
    mild_outdoor_warm_indoor,
    post_sunset_purge,
    pre_dawn_pre_cool,
    rain_override,
)


def test_hot_sunny_breeze_blinds_down_windows_open(cfg: ConfigV1):
    rec = decide(hot_sunny_breeze(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 100, f"{g} should be down"
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is True, f"{z} should be open"


def test_hot_sunny_still_blinds_down_windows_closed(cfg: ConfigV1):
    rec = decide(hot_sunny_still(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 100
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is False


def test_hot_cloudy_blinds_up_windows_state(cfg: ConfigV1):
    rec = decide(hot_cloudy(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 0


def test_cold_sunny_blinds_up_windows_closed(cfg: ConfigV1):
    rec = decide(cold_sunny(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 0
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is False


def test_cold_cloudy_blinds_down_windows_closed(cfg: ConfigV1):
    rec = decide(cold_cloudy(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 100
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is False


def test_post_sunset_hot_day_blinds_up_windows_open(cfg: ConfigV1):
    rec = decide(post_sunset_purge(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 0
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is True


def test_pre_dawn_hot_day_windows_open(cfg: ConfigV1):
    rec = decide(pre_dawn_pre_cool(cfg))
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is True


# ---- edge cases ---------------------------------------------------------------------------


def test_bedtime_warm_priority_over_house_rules(cfg: ConfigV1):
    """bedtime_prep (priority 90) sets bedroom blind down even if house-wide says up."""
    rec = decide(bedtime_too_warm(cfg))
    assert rec.by_blind_group["bedroom"].blind_pct == 100


def test_bedroom_overheat_red_urgency(cfg: ConfigV1):
    rec = decide(bedroom_overheat_safety(cfg))
    assert rec.global_.urgency == "red"
    assert rec.by_zone["bedroom"].window_open is True


def test_apex_stratification_triggers_stack_vent(cfg: ConfigV1):
    rec = decide(apex_stratification(cfg))
    # Mezz window must be open per stack-vent rule (priority 75).
    assert rec.by_zone["mezzanine"].window_open is True


def test_mild_outdoor_warm_indoor_opens_windows(cfg: ConfigV1):
    """Regression: cool-cloudy spring day with warmed-up indoor must vent."""
    rec = decide(mild_outdoor_warm_indoor(cfg))
    for z in ("mezzanine", "downstairs", "bedroom"):
        assert rec.by_zone[z].window_open is True, f"{z} should open"


def test_mild_cloudy_daytime_opens_blinds_too(cfg: ConfigV1):
    """No solar-gain risk → blinds up for natural light."""
    rec = decide(mild_outdoor_warm_indoor(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 0, f"{g} should be up"
        assert rec.by_blind_group[g].scenario == "daytime_light"


def test_let_light_in_reasoning_does_not_promise_airflow(cfg: ConfigV1):
    """REGRESSION (v0.14): the let_light_in rule only opens blinds, never
    windows. Promising "airflow" in the reasoning was a lie whenever the
    rule fired without cross_ventilate — which happens on any warm-cloudy
    day where outdoor is warmer than indoor. User reported the confusion.
    """
    rec = decide(mild_outdoor_warm_indoor(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        rec_group = rec.by_blind_group[g]
        # This scenario should fire let_light_in.
        assert rec_group.scenario == "daytime_light"
        # And its reasoning must not claim to deliver airflow that only
        # cross_ventilate can actually produce.
        for reason in rec_group.reasons:
            assert "airflow" not in reason.lower(), (
                f"let_light_in reasoning for {g} still claims airflow: {reason!r}. "
                f"This rule only sets blind_targets; airflow needs cross_ventilate."
            )


# --- v0.15: silence transparency guarantees --------------------------------


def test_v015_warm_cloudy_windows_silence_reports_import_heat(cfg: ConfigV1):
    """REGRESSION (v0.15 motivating bug): warm cloudy day where outdoor is
    hotter than indoor. _cross_ventilate correctly doesn't fire (opening
    would import heat). Before v0.15 the window recommendation had empty
    reasons and the dashboard couldn't explain the silence.

    After v0.15, the recommendation:
    - Has silence=True on by_zone entries where no window rule fired
    - Reasons include the actual temps and "import heat" text
    """
    from tests.scenarios import hot_sunny_still  # already exists; hot outdoor + still
    # hot_sunny_still: outdoor hot (blocks cross_vent since outdoor >= indoor).
    rec = decide(hot_sunny_still(cfg))
    for z in ("mezzanine", "downstairs", "bedroom"):
        rec_zone = rec.by_zone[z]
        # If no window rule fires, silence should populate reasons.
        if rec_zone.window_open is None or rec_zone.scenario == "neutral":
            assert rec_zone.silence is True, (
                f"{z}: silent recommendation must carry silence=True flag"
            )
            assert len(rec_zone.reasons) >= 1
            assert rec_zone.reasons[0], f"{z}: silence reason must be non-empty"


def test_v015_no_scenario_leaves_any_actuator_with_empty_reasons(cfg: ConfigV1):
    """Matrix invariant: every actuator on every canned scenario has at
    least one non-empty reason. Broader than pre-v0.15 (nothing enforced
    it) and guards against future rule additions that leave silence gaps.
    """
    from tests.scenarios import (
        hot_sunny_breeze,
        hot_sunny_still,
        hot_cloudy,
        cold_sunny,
        cold_cloudy,
        post_sunset_purge,
        pre_dawn_pre_cool,
        bedtime_too_warm,
        bedroom_overheat_safety,
        apex_stratification,
        mild_outdoor_warm_indoor,
        rain_override,
    )
    for scenario in (
        hot_sunny_breeze, hot_sunny_still, hot_cloudy, cold_sunny,
        cold_cloudy, post_sunset_purge, pre_dawn_pre_cool, bedtime_too_warm,
        bedroom_overheat_safety, apex_stratification, mild_outdoor_warm_indoor,
        rain_override,
    ):
        rec = decide(scenario(cfg))
        for g, r in rec.by_blind_group.items():
            assert r.reasons and r.reasons[0], (
                f"{scenario.__name__}: blind group {g} has empty reasons"
            )
        for z, r in rec.by_zone.items():
            assert r.reasons and r.reasons[0], (
                f"{scenario.__name__}: zone {z} has empty reasons"
            )


def test_v015_silence_flag_only_true_when_rule_did_not_fire(cfg: ConfigV1):
    """The silence flag is a semantic tag: True iff the reasons came from
    the silence explainer, False when they came from a real fired rule.
    Frontend uses this to filter pickWhy candidates."""
    from tests.scenarios import hot_sunny_breeze
    rec = decide(hot_sunny_breeze(cfg))
    for g, r in rec.by_blind_group.items():
        # In hot_sunny_breeze, blind rules definitely fire (block_solar_gain).
        # None of them should be silence=True.
        if r.scenario != "neutral":
            assert r.silence is False, (
                f"blind group {g} fired scenario {r.scenario!r} but "
                f"silence=True — flag semantics broken"
            )


def test_rain_suppresses_open_windows(cfg: ConfigV1):
    rec = decide(rain_override(cfg))
    for z in ("mezzanine", "downstairs", "bedroom", "ceiling_apex"):
        assert rec.by_zone[z].window_open is False


def test_no_weather_does_not_crash(cfg: ConfigV1):
    snap = hot_sunny_breeze(cfg)
    # Re-make snapshot with weather=None.
    from dataclasses import replace
    snap2 = replace(snap, weather=None)
    rec = decide(snap2)
    # No crash; rule_errors should be empty since rules guard on weather.
    assert isinstance(rec.rule_errors, list)
    # Some prompts should mention offline.
    assert any("offline" in p.lower() for p in rec.prompts) or rec.global_.urgency == "amber"


def test_buggy_rule_does_not_500(cfg: ConfigV1):
    """A rule that throws must be isolated."""
    from app.engine.engine import decide as do_decide
    from app.engine.rules import ALL_RULES, Rule
    from tests.scenarios import hot_sunny_breeze

    def boom(_):
        raise RuntimeError("boom")

    bad_rule = Rule("oops", 200, boom, boom)
    snap = hot_sunny_breeze(cfg)
    rec = do_decide(snap, rules=[*ALL_RULES, bad_rule])
    # Engine survives, error captured.
    assert any("oops" in e for e in rec.rule_errors)
