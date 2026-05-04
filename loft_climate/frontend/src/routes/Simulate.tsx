import { useState } from "react";

import { api } from "../api/client";
import { useScenarios } from "../api/hooks";
import type { SimulateResponse } from "../api/types";
import { Card } from "../components/glass/Card";
import { RecommendationsPanel } from "../components/RecommendationsPanel";
import { ScenarioBadge } from "../components/ScenarioBadge";

export function Simulate() {
  const { data: list } = useScenarios();
  const [selected, setSelected] = useState<string>("");
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    if (!selected) return;
    setRunning(true);
    try {
      const data = await api.post<SimulateResponse>("/api/simulate", {
        scenario_name: selected,
      });
      setResult(data);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Simulate</h1>
      <p className="text-sm opacity-70 max-w-2xl">
        Run the engine against a canned scenario to verify the matrix. Useful for
        eyeballing rule edits without waiting for real conditions.
      </p>
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="bg-white/5 border border-white/10 rounded px-2 py-2 text-sm"
          >
            <option value="">— pick a scenario —</option>
            {(list?.scenarios ?? []).map((s) => (
              <option key={s} value={s}>{s.replaceAll("_", " ")}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={run}
            disabled={!selected || running}
            className="glass-strong px-4 py-2 hover:bg-white/15 disabled:opacity-50"
          >
            {running ? "Running…" : "Run"}
          </button>
        </div>
      </Card>
      {result && (
        <>
          <ScenarioBadge
            scenario={result.recommendations.global.scenario}
            urgency={result.recommendations.global.urgency}
            prompts={result.recommendations.prompts}
          />
          <RecommendationsPanel rec={result.recommendations} />
        </>
      )}
    </div>
  );
}
