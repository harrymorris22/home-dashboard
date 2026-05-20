export type Urgency = "green" | "amber" | "red";

// Strict adherence (sports-hud, design.md):
// Single accent (tertiary #00E676) reserved exclusively for RED — the highest
// severity. Lower severities communicate via shape, weight, and typography —
// not colour. See globals.css `.urgency-*` classes for the typography rules.
export const urgencyClass: Record<Urgency, string> = {
  green: "bg-secondary/40",
  amber: "bg-primary",
  red: "bg-tertiary",
};

export const urgencyText: Record<Urgency, string> = {
  green: "urgency-green",
  amber: "urgency-amber",
  red: "urgency-red",
};

const RANK: Record<Urgency, number> = { green: 0, amber: 1, red: 2 };

export function maxUrgency(values: Urgency[]): Urgency {
  return values.reduce<Urgency>(
    (acc, v) => (RANK[v] > RANK[acc] ? v : acc),
    "green",
  );
}
