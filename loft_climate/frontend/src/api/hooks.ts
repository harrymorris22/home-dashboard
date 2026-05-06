import useSWR from "swr";

import { fetcher } from "./client";
import type { HistoryResponse, StateResponse } from "./types";

export function useDashboardState(refreshInterval = 60_000) {
  return useSWR<StateResponse>("/api/state", fetcher, { refreshInterval });
}

export function useHistory(days = 7) {
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 3600 * 1000);
  const path = `/api/history?start=${start.toISOString()}&end=${end.toISOString()}`;
  return useSWR<HistoryResponse>(path, fetcher, { refreshInterval: 5 * 60_000 });
}

export function useConfig() {
  return useSWR<unknown>("/api/config", fetcher);
}
