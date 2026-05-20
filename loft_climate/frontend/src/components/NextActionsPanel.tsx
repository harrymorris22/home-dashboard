import type { NextAction } from "../api/types";
import { Card } from "../_shared/Card";

const ACTUATOR_LABEL: Record<string, string> = {
  "blind:mezz": "Office blinds",
  "blind:downstairs": "Downstairs blinds",
  "blind:bedroom": "Bedroom blinds",
  "window:mezzanine": "Office window",
  "window:downstairs": "Downstairs window",
  "window:ceiling_apex": "Apex window",
  "window:bedroom": "Bedroom window",
};

function formatLocalTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDelta(iso: string, now: Date = new Date()): string {
  const ms = new Date(iso).getTime() - now.getTime();
  const minutes = Math.round(ms / 60000);
  if (minutes < 0) return "now";
  if (minutes < 60) return `in ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  if (rem === 0) return `in ${hours}h`;
  return `in ${hours}h${rem}m`;
}

function describeTransition(t: NextAction): string {
  const label = ACTUATOR_LABEL[t.actuator] ?? t.actuator;
  if (t.actuator.startsWith("blind:")) {
    const to = Number(t.to);
    const verb = to >= 75 ? "down" : to <= 25 ? "up" : `${to}%`;
    return `${label} → ${verb} (${to}%)`;
  }
  return `${label} → ${t.to}`;
}

export function NextActionsPanel({ actions }: { actions: NextAction[] }) {
  if (!actions || actions.length === 0) return null;

  // Group by timestamp so multiple simultaneous transitions read as one event.
  const groups = new Map<string, NextAction[]>();
  for (const a of actions) {
    const arr = groups.get(a.ts);
    if (arr) arr.push(a);
    else groups.set(a.ts, [a]);
  }
  const grouped = Array.from(groups.entries()).slice(0, 3);

  return (
    <Card>
      <h2 className="hud-label mb-3">Next actions</h2>
      <ul className="space-y-3">
        {grouped.map(([ts, items]) => {
          const reason = items.find((i) => i.reasoning)?.reasoning ?? "";
          return (
            <li key={ts} className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-bold text-primary">{formatLocalTime(ts)}</span>
                <span className="text-xs text-secondary">{formatDelta(ts)}</span>
              </div>
              <ul className="text-sm space-y-0.5 text-primary">
                {items.map((it, i) => (
                  <li key={`${ts}-${i}`}>• {describeTransition(it)}</li>
                ))}
              </ul>
              {reason && <p className="text-xs text-secondary">Why: {reason}</p>}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
