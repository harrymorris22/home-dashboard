import useSWR from "swr";

import { fetcher } from "./client";
import type { HistoryResponse, StateResponse, SunshineScaleItem } from "./types";

export function useDashboardState(refreshInterval = 60_000) {
  return useSWR<StateResponse>("/api/state", fetcher, { refreshInterval });
}

export function useHistory(days = 7) {
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 3600 * 1000);
  const path = `/api/history?start=${start.toISOString()}&end=${end.toISOString()}`;
  return useSWR<HistoryResponse>(path, fetcher, { refreshInterval: 5 * 60_000 });
}

export function useScenarios() {
  return useSWR<{ scenarios: string[] }>("/api/simulate/scenarios", fetcher);
}

export function useConfig() {
  return useSWR<unknown>("/api/config", fetcher);
}

export function useLatestReadings() {
  return useSWR<{ zones: Record<string, { ts: string; temp_c: number; humidity_pct: number | null; lux_indoor: number | null }> }>(
    "/api/readings/latest",
    fetcher,
  );
}

export function useSunshineScale() {
  return useSWR<{ items: SunshineScaleItem[] }>("/api/sunshine/scale", fetcher);
}

export function useLatestSunshine() {
  return useSWR<{ sunshine: { ts: string; lux: number; scale: number | null } | null }>(
    "/api/sunshine/latest",
    fetcher,
  );
}
