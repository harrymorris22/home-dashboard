from app.engine.heat_index import apparent_temp_c


def test_dry_air_returns_temp():
    assert apparent_temp_c(20.0, 50) == 20.0


def test_muggy_warm_nudges_up():
    val = apparent_temp_c(24.0, 70)
    assert abs(val - 24.48) < 0.01


def test_dry_warm_nudges_down():
    val = apparent_temp_c(24.0, 30)
    assert abs(val - 23.52) < 0.01


def test_hot_humid():
    val = apparent_temp_c(28.0, 80)
    assert abs(val - 29.20) < 0.01


def test_below_18_no_correction():
    assert apparent_temp_c(18.0, 90) == 18.0
    assert apparent_temp_c(15.0, 100) == 15.0


def test_humidity_none_returns_temp():
    assert apparent_temp_c(24.0, None) == 24.0
