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

export function useClimate() {
  return useSWR<ClimateData>("/api/widgets/climate", fetcher, {
    refreshInterval: 60_000,
  });
}

export function useStock(ticker = "LQQ3.L") {
  return useSWR<StockData>(`/api/widgets/stock/${ticker}`, fetcher, {
    refreshInterval: 60_000,
  });
}

export function useCalendar() {
  return useSWR<CalendarData>("/api/widgets/calendar/next", fetcher, {
    refreshInterval: 5 * 60_000,
  });
}

export function useSystem() {
  return useSWR<SystemHealth>("/api/widgets/system/health", fetcher, {
    refreshInterval: 30_000,
  });
}
