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
    """No solar-gain risk → blinds up for natural light + airflow."""
    rec = decide(mild_outdoor_warm_indoor(cfg))
    for g in ("mezz", "downstairs", "bedroom"):
        assert rec.by_blind_group[g].blind_pct == 0, f"{g} should be up"
        assert rec.by_blind_group[g].scenario == "daytime_light"


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
