from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config.schema import ConfigV1
from app.engine.types import Snapshot
from app.sensors.source import (
    ActuatorStateSource,
    OutdoorSource,
    SensorSource,
    SunshineSource,
)
from app.sun import calculator as suncalc
from app.weather import cache as weather_cache
from app.weather.feels_like import apparent_temp_outdoor


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
        # Override OWM temp/humidity with on-building reading when available.
        if weather is not None and self.outdoor_source is not None:
            outdoor = self.outdoor_source.latest()
            if outdoor is not None:
                feels = apparent_temp_outdoor(
                    outdoor.temp_c,
                    outdoor.humidity_pct,
                    weather.wind_speed_mps,
                )
                weather = replace(
                    weather,
                    temp_c=outdoor.temp_c,
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
        )
