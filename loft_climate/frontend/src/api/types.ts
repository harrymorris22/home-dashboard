import type { Urgency } from "../lib/urgency";

export type ZoneId = "mezzanine" | "downstairs" | "ceiling_apex" | "bedroom";
export type BlindGroupId = "mezz" | "downstairs" | "bedroom";

export const ZONE_IDS: ZoneId[] = ["mezzanine", "downstairs", "ceiling_apex", "bedroom"];
export const BLIND_GROUP_IDS: BlindGroupId[] = ["mezz", "downstairs", "bedroom"];

export type SensorReading = {
  temp_c: number;
  humidity_pct: number | null;
  lux_indoor: number | null;
  ts: string;
  age_seconds: number;
};

export type WeatherView = {
  fetched_at: string;
  stale: boolean;
  temp_c: number;
  feels_like_c: number;
  humidity_pct: number;
  cloud_cover_pct: number;
  wind_speed_mps: number;
  wind_gust_mps: number | null;
  uvi: number;
  conditions: string;
  precip_now: boolean;
  sunrise: string;
  sunset: string;
};

export type SunView = {
  elevation_deg: number;
  azimuth_deg: number;
  sunrise: string;
  sunset: string;
  is_daylight: boolean;
};

export type BlindGroupRecommendation = {
  group: BlindGroupId;
  blind_pct: number;
  urgency: Urgency;
  scenario: string;
  reasons: string[];
};

export type ZoneWindowRecommendation = {
  zone: ZoneId;
  window_open: boolean | null;
  urgency: Urgency;
  scenario: string;
  reasons: string[];
};

export type Recommendations = {
  ts: string;
  global: { scenario: string; urgency: Urgency };
  by_blind_group: Record<BlindGroupId, BlindGroupRecommendation>;
  by_zone: Record<ZoneId, ZoneWindowRecommendation>;
  prompts: string[];
  rule_errors: string[];
};

export type SunshineView = { lux: number };

export type CurrentState = {
  blinds: Record<string, number>;  // group -> 0..100
  windows: Record<string, boolean>; // zone -> open
};

export type NextAction = {
  ts: string;
  actuator: string;     // "blind:mezz" or "window:bedroom"
  from: number | string | null;
  to: number | string;
  scenario: string;
  reasoning: string;
};

export type StateResponse = {
  ts: string;
  sensors: Record<string, SensorReading>;
  weather: WeatherView | null;
  sun: SunView;
  sunshine: SunshineView | null;
  current_state: CurrentState;
  recommendations: Recommendations;
  next_actions: NextAction[];
};

export type SunshineScaleItem = { step: number; label: string; lux: number };

export type SimulateResponse = {
  scenario_name: string;
  recommendations: Recommendations;
};

export type HistoryPoint = {
  ts: string;
  zone: string;
  temp_c: number;
  humidity_pct: number | null;
  lux_indoor: number | null;
};

export type HistoryResponse = {
  points: HistoryPoint[];
  recommendations: Array<{
    ts: string;
    actuator: string;
    value: string;
    urgency: Urgency;
    scenario: string;
    reasoning: string;
  }>;
};
