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

export function formatPercent(p: number | null | undefined, decimals = 1): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  return `${p.toFixed(decimals)}%`;
}

export function formatPrice(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const symbol = currency === "GBP" ? "£" : currency === "USD" ? "$" : currency === "EUR" ? "€" : "";
  return symbol ? `${symbol}${value.toFixed(2)}` : `${value.toFixed(2)} ${currency}`;
}
