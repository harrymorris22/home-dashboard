import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { HistoryResponse } from "../api/types";
import { Card } from "./glass/Card";

type Metric = "temp_c" | "humidity_pct" | "lux_indoor";

const METRIC_LABEL: Record<Metric, string> = {
  temp_c: "Temperature (°C)",
  humidity_pct: "Humidity (%)",
  lux_indoor: "Lux",
};

// Strict adherence: tertiary (#00E676) is reserved for RED urgency only.
// Chart series are distinguished by stroke pattern + weight, all rendered
// in primary/secondary. This keeps the single-accent rule load-bearing.
const SERIES_STYLE: Record<string, { stroke: string; dash?: string; width: number }> = {
  mezzanine: { stroke: "#0E1016", width: 2.5 },
  downstairs: { stroke: "#0E1016", dash: "6 4", width: 2 },
  ceiling_apex: { stroke: "#5B6270", width: 2 },
  bedroom: { stroke: "#5B6270", dash: "2 4", width: 2 },
};

export function HistoryChart({ data }: { data: HistoryResponse | undefined }) {
  const [metric, setMetric] = useState<Metric>("temp_c");
  const [hidden, setHidden] = useState<Record<string, boolean>>({});

  const points = data?.points ?? [];

  const chartData = useMemo(() => {
    const byTs: Record<string, Record<string, number | string>> = {};
    for (const p of points) {
      if (!byTs[p.ts]) byTs[p.ts] = { ts: p.ts };
      const v = (p as any)[metric];
      if (v !== null && v !== undefined) byTs[p.ts][p.zone] = v;
    }
    return Object.values(byTs).sort((a, b) =>
      String(a.ts) < String(b.ts) ? -1 : 1,
    );
  }, [points, metric]);

  const zonesWithData = Array.from(new Set(points.map((p) => p.zone)));

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h2 className="hud-label flex-1">
          History — last 7 days
        </h2>
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value as Metric)}
          className="bg-surface text-primary border border-secondary/40 rounded px-2 py-1 text-sm"
        >
          {Object.entries(METRIC_LABEL).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <div className="flex gap-2 text-xs">
          {zonesWithData.map((z) => {
            const style = SERIES_STYLE[z];
            return (
              <button
                key={z}
                type="button"
                onClick={() => setHidden((p) => ({ ...p, [z]: !p[z] }))}
                className={`px-2 py-1 rounded uppercase tracking-label font-bold border ${
                  hidden[z]
                    ? "border-secondary/30 text-secondary"
                    : "border-primary text-primary"
                }`}
              >
                {z}
                {style?.dash && (
                  <span className="ml-1 inline-block align-middle" aria-hidden>
                    <svg width="14" height="6">
                      <line
                        x1="0"
                        y1="3"
                        x2="14"
                        y2="3"
                        stroke={style.stroke}
                        strokeWidth={style.width}
                        strokeDasharray={style.dash}
                      />
                    </svg>
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 5, right: 12, bottom: 5, left: 0 }}>
            <CartesianGrid stroke="rgba(91,98,112,0.18)" strokeDasharray="3 3" />
            <XAxis
              dataKey="ts"
              tick={{ fontSize: 10, fill: "#5B6270" }}
              tickFormatter={(t: string) =>
                new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
              }
              minTickGap={32}
            />
            <YAxis tick={{ fontSize: 10, fill: "#5B6270" }} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{
                background: "#FFFFFF",
                border: "1px solid #5B6270",
                borderRadius: "4px",
                color: "#0E1016",
              }}
              labelFormatter={(t: string) => new Date(t).toLocaleString()}
            />
            {zonesWithData.map((z) => {
              if (hidden[z]) return null;
              const style = SERIES_STYLE[z] ?? { stroke: "#0E1016", width: 2 };
              return (
                <Line
                  key={z}
                  type="monotone"
                  dataKey={z}
                  stroke={style.stroke}
                  strokeDasharray={style.dash}
                  dot={false}
                  strokeWidth={style.width}
                  isAnimationActive={false}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {chartData.length === 0 && (
        <p className="text-sm text-secondary mt-3">
          No data yet — submit a few manual readings to see the chart populate.
        </p>
      )}
    </Card>
  );
}
