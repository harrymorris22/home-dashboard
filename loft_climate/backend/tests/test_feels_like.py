from app.weather.feels_like import apparent_temp_outdoor


def test_calm_warm_with_humidity():
    # 25°C, 60% RH, calm → noticeably warmer feel.
    val = apparent_temp_outdoor(25.0, 60, 0.0)
    assert val > 25.0
    assert val < 30.0


def test_cool_windy_with_humidity():
    # 17°C, 70% RH, 5 m/s breeze → cooler.
    val = apparent_temp_outdoor(17.0, 70, 5.0)
    assert val < 17.0


def test_no_humidity_falls_back_to_wind_only():
    # No humidity reading: just T - 0.7v - 4.
    val = apparent_temp_outdoor(20.0, None, 3.0)
    assert abs(val - (20.0 - 0.7 * 3.0 - 4.0)) < 1e-6
