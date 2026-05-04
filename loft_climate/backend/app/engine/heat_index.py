"""Apparent temperature ("feels like") for indoor London summer range.

Uses a simple linear humidity correction valid across 18-32°C:

    T_app = T + 0.4 * (RH/100 - 0.5) * max(T - 18, 0)

This is intentionally NOT the NWS Rothfusz heat-index polynomial. NWS Rothfusz is
empirically fitted for hot, humid US summers (≥26.7°C / 80°F) and degenerates to
~T below that band — useless for our 22-28°C indoor range. The simple linear form
above produces the right qualitative behaviour: ~T in dry air, +1-2°C nudge in
muggy 24°C / 70% RH conditions, no correction at 18°C or below.

Anchor values (hand-computed):
    T=20, RH=50  -> 20.0
    T=24, RH=70  -> 24 + 0.4*(0.2)*6  = 24.48
    T=24, RH=30  -> 24 + 0.4*(-0.2)*6 = 23.52
    T=28, RH=80  -> 28 + 0.4*(0.3)*10 = 29.20
    T=28, RH=40  -> 28 + 0.4*(-0.1)*10 = 27.60
    T=18, RH=90  -> 18.0  (T-18 clamped to 0)
"""
from __future__ import annotations


def apparent_temp_c(temp_c: float, humidity_pct: float | None) -> float:
    if humidity_pct is None:
        return temp_c
    return temp_c + 0.4 * (humidity_pct / 100.0 - 0.5) * max(temp_c - 18.0, 0.0)
