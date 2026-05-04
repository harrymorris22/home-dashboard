import { useDashboardState } from "../api/hooks";
import { ActionPanel } from "../components/ActionPanel";
import { NextActionsPanel } from "../components/NextActionsPanel";
import { WeatherStrip } from "../components/WeatherStrip";
import { ZoneGrid } from "../components/ZoneGrid";
import { RecommendationsPanel } from "../components/RecommendationsPanel";
import { Card } from "../components/glass/Card";
import { relativeTime } from "../lib/time";

export function Dashboard() {
  const { data, error, isLoading } = useDashboardState();

  if (isLoading)
    return <Card><p className="opacity-70">Loading…</p></Card>;
  if (error || !data)
    return (
      <Card className="border-rose-500/40">
        <p className="text-rose-300">Could not load /api/state.</p>
      </Card>
    );

  return (
    <div className="space-y-4">
      <ActionPanel rec={data.recommendations} currentState={data.current_state} />
      <NextActionsPanel actions={data.next_actions} />
      <WeatherStrip weather={data.weather} sun={data.sun} sunshine={data.sunshine} />
      <ZoneGrid sensors={data.sensors} recommendations={data.recommendations} />
      <RecommendationsPanel rec={data.recommendations} />
      <Card className="text-xs opacity-60 text-center">
        Last refresh {relativeTime(data.ts)}
      </Card>
    </div>
  );
}
