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
    return <Card><p className="text-secondary">Loading…</p></Card>;
  if (error || !data)
    return (
      <Card className="border-2 border-primary">
        <p className="text-primary uppercase tracking-label font-bold">Could not load /api/state.</p>
      </Card>
    );

  return (
    <div className="space-y-4">
      <ActionPanel rec={data.recommendations} currentState={data.current_state} />
      <NextActionsPanel actions={data.next_actions} />
      <WeatherStrip weather={data.weather} sun={data.sun} sunshine={data.sunshine} />
      <ZoneGrid sensors={data.sensors} recommendations={data.recommendations} />
      <RecommendationsPanel rec={data.recommendations} />
      <Card className="text-xs text-secondary text-center">
        Last refresh {relativeTime(data.ts)}
      </Card>
    </div>
  );
}
