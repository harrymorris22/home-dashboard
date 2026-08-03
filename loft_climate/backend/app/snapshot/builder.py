from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config.schema import ConfigV1
from app.db import repo
from app.engine.types import Snapshot
from app.sensors.source import (
    ActuatorStateSource,
    OutdoorSource,
    SensorSource,
    SunshineSource,
)
from app.sun import calculator as suncalc
from app.weather import cache as weather_cache
from app.weather.correction import corrected_outdoor_temp
from app.weather.feels_like import apparent_temp_outdoor

log = logging.getLogger(__name__)


class SnapshotBuilder:
    """Assembles a Snapshot from sensor source + weather cache + sun calculator + config."""

    def __init__(
        self,
        session: Session,
        sensor_source: SensorSource,
        cfg: ConfigV1,
        sunshine_source: SunshineSource | None = None,
        actuator_state_source: ActuatorStateSource | None = None,
        outdoor_source: OutdoorSource | None = None,
    ) -> None:
        self.session = session
        self.sensor_source = sensor_source
        self.sunshine_source = sunshine_source
        self.actuator_state_source = actuator_state_source
        self.outdoor_source = outdoor_source
        self.cfg = cfg

    async def build(self, now: datetime | None = None) -> Snapshot:
        now = now or datetime.now(tz=timezone.utc)
        zones = self.sensor_source.latest()
        weather = await weather_cache.get_or_fetch(self.session, self.cfg)
        # Preserve the raw Met.no reading before any override so the UI can
        # display it alongside the sensor reading. None when weather is
        # offline (rules already handle that path).
        outdoor_forecast_c: float | None = weather.temp_c if weather else None
        outdoor_raw_c: float | None = None
        # Override OWM temp/humidity with on-building reading when available.
        if weather is not None and self.outdoor_source is not None:
            outdoor = self.outdoor_source.latest()
            if outdoor is not None:
                outdoor_raw_c = outdoor.temp_c
                # v0.20: strip the solar-heating artifact from the SwitchBot
                # reading before feeding it to the rules. Falls through to
                # raw when correction is disabled or no calibration exists.
                effective_temp = _apply_correction(
                    self.session, self.cfg, outdoor_raw_c, weather.cloud_cover_pct, now
                )
                feels = apparent_temp_outdoor(
                    effective_temp,
                    outdoor.humidity_pct,
                    weather.wind_speed_mps,
                )
                weather = replace(
                    weather,
                    temp_c=effective_temp,
                    humidity_pct=(
                        outdoor.humidity_pct
                        if outdoor.humidity_pct is not None
                        else weather.humidity_pct
                    ),
                    feels_like_c=feels,
                )
        sun = suncalc.compute(now, self.cfg)
        sw_lux: float | None = None
        if self.sunshine_source is not None:
            r = self.sunshine_source.latest()
            sw_lux = r.lux if r is not None else None
        current_blind: dict[str, int] = {}
        current_window: dict[str, bool] = {}
        if self.actuator_state_source is not None:
            state = self.actuator_state_source.latest()
            current_blind = dict(state.blind_pct)
            current_window = dict(state.window_open)
        return Snapshot(
            now=now,
            zones=zones,
            weather=weather,
            sun=sun,
            config=self.cfg,
            sw_lux=sw_lux,
            current_blind=current_blind,
            current_window=current_window,
            outdoor_raw_c=outdoor_raw_c,
            outdoor_forecast_c=outdoor_forecast_c,
        )


def _apply_correction(
    session: Session,
    cfg: ConfigV1,
    raw_temp: float,
    cloud_cover_pct: float | None,
    now: datetime,
) -> float:
    """Look up the latest fitted bias curve and correct the sensor reading.

    Never raises: on any error (no calibration row, bad JSON, missing tz)
    returns the raw reading and logs a warning. That way a corrupt row
    can't break the whole snapshot pipeline.
    """
    if cfg.outdoor.correction == "sensor_only":
        return raw_temp
    try:
        row = repo.latest_outdoor_calibration(session)
        if row is None:
            return raw_temp
        bias_by_hour = json.loads(row.bias_by_hour_json)
        tz = ZoneInfo(cfg.location.timezone)
        hour_local = now.astimezone(tz).hour
        return corrected_outdoor_temp(
            raw_temp,
            hour_local,
            cloud_cover_pct,
            bias_by_hour,
            cfg.outdoor.microclimate_baseline_c,
            cfg.outdoor.clearness_floor,
        )
    except Exception:
        log.exception("[snapshot-builder] outdoor correction failed; using raw")
        return raw_temp
