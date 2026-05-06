import { Card } from "./glass/Card";
import type { SunView, SunshineView, WeatherView } from "../api/types";
import { formatLux, formatTemp } from "../lib/format";
import { formatTime } from "../lib/time";

export function WeatherStrip({
  weather,
  sun,
  sunshine,
}: {
  weather: WeatherView | null;
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
  return (
    <Card className="flex items-center flex-wrap gap-x-8 gap-y-2 text-sm text-primary">
      <span className="flex items-center gap-2">
        <span className="hud-label">Outdoor</span>
        <span className="font-bold">{formatTemp(weather.temp_c)}</span>
        <span className="text-secondary">feels {formatTemp(weather.feels_like_c)}</span>
      </span>
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
