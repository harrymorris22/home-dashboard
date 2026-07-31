"""Correction of the SwitchBot outdoor sensor for solar heating on its casing.

Empirically (see v0.19 calibration data) the SwitchBot outdoor sensor
reads up to +8°C over true air temp during morning hours when the sun
lands on its plastic case. The bias is asymmetric: nearly zero in the
afternoon and evening, peaks at 09-10 BST, holds a small overnight
offset (~+1.5°C) from urban microclimate.

Model:

    corrected = raw − excess_bias(hour) × clearness

where
    excess_bias(hour) = max(0, bias_by_hour[hour] − microclimate_baseline_c)
    clearness         = max(clearness_floor, 1 − cloud_cover_pct / 100)

Rationale for the two-component split:

- The overnight/no-sun bias is *real* microclimate — the building sits
  in a slightly warmer pocket than the Met.no grid cell. We preserve it
  by only subtracting bias *above* the baseline.
- The morning bias spike is the sensor artifact. It scales with how much
  sun is actually landing on the sensor casing, which is roughly
  proportional to clear-sky fraction. Cloud cover from Met.no is the
  best available proxy — sw_lux is inside the window and reads zero when
  blinds are down; sun_on_sw is SW-glazing geometry which peaks in the
  afternoon, not the morning when the sensor bakes.
- ``clearness_floor`` (default 0.15) keeps a small correction alive even
  on fully-overcast days — diffuse sky radiation still hits the casing.

This is a pure function of numbers. No I/O, no time lookups. The caller
resolves the current hour_bst and cloud_cover_pct and passes them in.
"""
from __future__ import annotations


def corrected_outdoor_temp(
    raw_temp_c: float,
    hour_bst: int,
    cloud_cover_pct: float | None,
    bias_by_hour: list[float] | None,
    microclimate_baseline_c: float,
    clearness_floor: float,
) -> float:
    """Return the corrected outdoor temp in °C.

    Falls through to ``raw_temp_c`` unchanged when:
    - ``bias_by_hour`` is None (no calibration fitted yet), or
    - the hour's bias is at or below the microclimate baseline (no
      excess to strip), or
    - cloud cover is unknown *and* we still apply the floor conservatively.

    Never raises: bad inputs degrade to the raw reading.
    """
    if bias_by_hour is None:
        return raw_temp_c
    if not (0 <= hour_bst < 24):
        return raw_temp_c
    if len(bias_by_hour) != 24:
        return raw_temp_c
    hour_bias = bias_by_hour[hour_bst]
    excess = hour_bias - microclimate_baseline_c
    if excess <= 0:
        # Overnight / already-below-baseline hours: no artifact to strip.
        return raw_temp_c
    if cloud_cover_pct is None:
        # Missing cloud data: apply conservatively — the floor keeps
        # correction alive at all, but we can't confirm it's a sunny day
        # so we don't ramp beyond the floor.
        clearness = clearness_floor
    else:
        clamped_cloud = max(0.0, min(100.0, cloud_cover_pct))
        clearness = max(clearness_floor, 1.0 - clamped_cloud / 100.0)
    return raw_temp_c - excess * clearness
