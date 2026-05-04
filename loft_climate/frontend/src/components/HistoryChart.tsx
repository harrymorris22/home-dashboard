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

const COLORS: Record<string, string> = {
  mezzanine: "#34d399",
  downstairs: "#60a5fa",
  ceiling_apex: "#f59e0b",
  bedroom: "#f472b6",
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
        <h2 className="text-sm uppercase tracking-wider opacity-70 flex-1">
          History — last 7 days
        </h2>
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value as Metric)}
          className="bg-white/5 border border-white/10 rounded px-2 py-1 text-sm"
        >
          {Object.entries(METRIC_LABEL).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <div className="flex gap-2 text-xs">
          {zonesWithData.map((z) => (
            <button
              key={z}
              type="button"
              onClick={() => setHidden((p) => ({ ...p, [z]: !p[z] }))}
              className={`px-2 py-1 rounded border ${
                hidden[z] ? "border-white/10 opacity-40" : "border-white/30"
              }`}
              style={{ color: COLORS[z] }}
            >
              {z}
            </button>
          ))}
        </div>
      </div>

      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 5, right: 12, bottom: 5, left: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
            <XAxis
              dataKey="ts"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickFormatter={(t: string) =>
                new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
              }
              minTickGap={32}
            />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "rgb(15 23 42 / 0.9)", border: "1px solid rgba(255,255,255,0.1)" }}
              labelFormatter={(t: string) => new Date(t).toLocaleString()}
            />
            {zonesWithData.map((z) =>
              hidden[z] ? null : (
                <Line
                  key={z}
                  type="monotone"
                  dataKey={z}
                  stroke={COLORS[z] || "#fff"}
                  dot={false}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              ),
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {chartData.length === 0 && (
        <p className="text-sm opacity-60 mt-3">
          No data yet — submit a few manual readings to see the chart populate.
        </p>
      )}
    </Card>
  );
}
