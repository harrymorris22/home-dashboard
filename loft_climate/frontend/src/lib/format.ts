export function formatTemp(t: number | null | undefined): string {
  if (t === null || t === undefined || Number.isNaN(t)) return "—";
  return `${t.toFixed(1)}°C`;
}

export function formatHumidity(h: number | null | undefined): string {
  if (h === null || h === undefined || Number.isNaN(h)) return "—";
  return `${Math.round(h)}%`;
}

export function formatLux(lux: number | null | undefined): string {
  if (lux === null || lux === undefined || Number.isNaN(lux)) return "—";
  if (lux >= 1000) return `${(lux / 1000).toFixed(1)}k lx`;
  return `${Math.round(lux)} lx`;
}

export function roundBlind(pct: number): number {
  if (pct <= 0) return 0;
  if (pct >= 100) return 100;
  // Round to nearest 25 for clear physical action.
  return Math.round(pct / 25) * 25;
}

export function formatBlind(pct: number): string {
  const rounded = roundBlind(pct);
  if (rounded === 0) return "Up (0%)";
  if (rounded === 100) return "Down (100%)";
  return `${rounded}%`;
}
