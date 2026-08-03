import { Card } from "../_shared/Card";
import type { OutdoorView, SunView, SunshineView, WeatherView } from "../api/types";
import { formatLux, formatTemp } from "../_shared/format";
import { formatTime } from "../_shared/time";

export function WeatherStrip({
  weather,
  outdoor,
  sun,
  sunshine,
}: {
  weather: WeatherView | null;
  outdoor: OutdoorView | null;
  sun: SunView;
  sunshine: SunshineView | null;
}) {
  if (weather === null) {
    return (
      <Card className="flex items-center justify-between flex-wrap gap-3 border-2 border-primary">
        <span className="hud-label">Weather offline</span>
        <span className="text-xs text-secondary">Recommendations limited to indoor signals.</span>
      </Card>
    );
  }
  // Only show the sensor/met/used breakdown when both underlying sources
  // are present. When there's no outdoor sensor override, the single
  // "Outdoor" figure IS Met.no directly and a breakdown would just
  // repeat it.
  const showBreakdown =
    outdoor !== null &&
    outdoor.raw_c !== null &&
    outdoor.forecast_c !== null &&
    outdoor.effective_c !== null;

  return (
    <Card className="flex items-center flex-wrap gap-x-8 gap-y-2 text-sm text-primary">
      <span className="flex items-center gap-2">
        <span className="hud-label">Outdoor</span>
        <span className="font-bold">{formatTemp(weather.temp_c)}</span>
        <span className="text-secondary">feels {formatTemp(weather.feels_like_c)}</span>
      </span>
      {showBreakdown && outdoor && (
        <span className="flex items-center gap-3 text-xs text-secondary">
          <span>
            <span className="hud-label mr-1">Sensor</span>
            {formatTemp(outdoor.raw_c!)}
          </span>
          <span aria-hidden="true">·</span>
          <span>
            <span className="hud-label mr-1">Met</span>
            {formatTemp(outdoor.forecast_c!)}
          </span>
          <span aria-hidden="true">·</span>
          <span>
            <span className="hud-label mr-1">Used</span>
            <span className="text-primary font-bold">{formatTemp(outdoor.effective_c!)}</span>
          </span>
          {outdoor.delta_c !== null && Math.abs(outdoor.delta_c) >= 0.1 && (
            <span
              title="Bias correction applied to the sensor reading"
              className="text-secondary"
            >
              ({outdoor.delta_c > 0 ? "+" : ""}
              {outdoor.delta_c.toFixed(1)}°C)
            </span>
          )}
        </span>
      )}
      <span>
        <span className="text-secondary">{weather.conditions}</span>{" "}
        <span className="text-secondary">· cloud {Math.round(weather.cloud_cover_pct)}%</span>
      </span>
      <span>
        <span className="hud-label">Wind</span> {weather.wind_speed_mps.toFixed(1)} m/s
      </span>
      <span>
        <span className="hud-label">UVI</span> {weather.uvi.toFixed(1)}
      </span>
      <span>
        <span className="hud-label">Sun</span> {sun.azimuth_deg.toFixed(0)}° az,{" "}
        {sun.elevation_deg.toFixed(0)}° el
      </span>
      {sunshine && (
        <span>
          <span className="hud-label">SW lux</span> {formatLux(sunshine.lux)}
        </span>
      )}
      <span>
        <span className="hud-label">Sunset</span> {formatTime(weather.sunset)}
      </span>
      {weather.stale && <span className="hud-label">stale</span>}
    </Card>
  );
}
