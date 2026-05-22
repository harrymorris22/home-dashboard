/** SWR hooks — one per widget. Refresh cadence matches widget volatility. */
import useSWR from "swr";

import { fetcher } from "./client";
import type { Urgency } from "../_shared/urgency";

export type ClimateData = {
  scenario: string;
  urgency: Urgency;
  bedroom_temp_c: number | null;
  prompt: string | null;
  ts: string;
  stale: boolean;
  last_success_at: string | null;
};

export type StockData = {
  ticker: string;
  price: number;
  currency: string;
  day_change_abs: number;
  day_change_pct: number;
  sparkline: number[];
  stale: boolean;
  last_success_at: string | null;
};

export type CalendarEvent = {
  title: string;
  starts_at: string;
  location: string | null;
  all_day: boolean;
};

export type CalendarData = {
  next: CalendarEvent | null;
  today: CalendarEvent[];
};

export type SystemHealth = {
  cpu_pct: number;
  cpu_temp_c: number | null;
  disk_pct: number;
  mem_pct: number;
  internet_24h_pct: number | null;
  lan_24h_pct: number | null;
  last_ping_ts: string | null;
};

// Cadences chosen per upstream volatility:
//   Climate — 10s, loft has live HA WS data; cheap to poll
//   Stock   — 60s, Yahoo data is 15–20min delayed anyway
//   Calendar — 2min, events change rarely
//   System  — 10s, psutil + SQLite aggregate is local & cheap
// revalidateOnFocus is SWR's default; making it explicit for clarity so
// the next reader doesn't wonder whether it's on.
const FOCUS = { revalidateOnFocus: true } as const;

export function useClimate() {
  return useSWR<ClimateData>("/api/widgets/climate", fetcher, {
    refreshInterval: 10_000,
    ...FOCUS,
  });
}

export function useStock(ticker = "LQQ3.L") {
  return useSWR<StockData>(`/api/widgets/stock/${ticker}`, fetcher, {
    refreshInterval: 60_000,
    ...FOCUS,
  });
}

export function useCalendar() {
  return useSWR<CalendarData>("/api/widgets/calendar/next", fetcher, {
    refreshInterval: 2 * 60_000,
    ...FOCUS,
  });
}

export function useSystem() {
  return useSWR<SystemHealth>("/api/widgets/system/health", fetcher, {
    refreshInterval: 10_000,
    ...FOCUS,
  });
}
