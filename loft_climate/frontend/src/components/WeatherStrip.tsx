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
      <Card className="flex items-center justify-between flex-wrap gap-3 border-amber-400/40">
        <span className="text-amber-300 text-sm uppercase tracking-wider">Weather offline</span>
        <span className="text-xs opacity-60">Recommendations limited to indoor signals.</span>
      </Card>
    );
  }
  return (
    <Card className="flex items-center flex-wrap gap-x-8 gap-y-2 text-sm">
      <span className="flex items-center gap-2">
        <span className="opacity-60">Outdoor</span>
        <span className="font-semibold">{formatTemp(weather.temp_c)}</span>
        <span className="opacity-60">feels {formatTemp(weather.feels_like_c)}</span>
      </span>
      <span>
        <span className="opacity-60">{weather.conditions}</span>{" "}
        <span className="opacity-60">· cloud {Math.round(weather.cloud_cover_pct)}%</span>
      </span>
      <span>
        <span className="opacity-60">Wind</span> {weather.wind_speed_mps.toFixed(1)} m/s
      </span>
      <span>
        <span className="opacity-60">UVI</span> {weather.uvi.toFixed(1)}
      </span>
      <span>
        <span className="opacity-60">Sun</span> {sun.azimuth_deg.toFixed(0)}° az,{" "}
        {sun.elevation_deg.toFixed(0)}° el
      </span>
      {sunshine && (
        <span>
          <span className="opacity-60">SW lux</span> {formatLux(sunshine.lux)}
        </span>
      )}
      <span>
        <span className="opacity-60">Sunset</span> {formatTime(weather.sunset)}
      </span>
      {weather.stale && <span className="text-amber-300">stale</span>}
    </Card>
  );
}
