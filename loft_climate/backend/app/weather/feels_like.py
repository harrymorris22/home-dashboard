"""Outdoor apparent temperature (Australian BoM formula).

Used when overriding OWM's feels_like_c with a real on-building sensor reading
that can't tell us about wind. Combines:
  - Sensor-measured temperature (°C)
  - Sensor-measured humidity (%)
  - OWM's wind speed (m/s)

  AT = T + 0.33·e − 0.70·v − 4.00
  e  = (RH/100)·6.105·exp(17.27·T / (237.7 + T))    (vapour pressure, hPa)

References: BoM ATSR-1994, used by Australian and several European met services
across our 0–35°C operating band. Less ad hoc than NWS Rothfusz at low temps.
"""
from __future__ import annotations

from math import exp


def apparent_temp_outdoor(
    temp_c: float, humidity_pct: float | None, wind_speed_mps: float
) -> float:
    if humidity_pct is None:
        # Fallback: ignore humidity term (still apply wind-chill term).
        e = 0.0
    else:
        e = (humidity_pct / 100.0) * 6.105 * exp(17.27 * temp_c / (237.7 + temp_c))
    return temp_c + 0.33 * e - 0.70 * wind_speed_mps - 4.00
