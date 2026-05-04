export type Urgency = "green" | "amber" | "red";

export const urgencyClass: Record<Urgency, string> = {
  green: "bg-emerald-400/80",
  amber: "bg-amber-400/80",
  red: "bg-rose-500/90",
};

export const urgencyText: Record<Urgency, string> = {
  green: "text-emerald-300",
  amber: "text-amber-300",
  red: "text-rose-300",
};

const RANK: Record<Urgency, number> = { green: 0, amber: 1, red: 2 };

export function maxUrgency(values: Urgency[]): Urgency {
  return values.reduce<Urgency>(
    (acc, v) => (RANK[v] > RANK[acc] ? v : acc),
    "green",
  );
}
