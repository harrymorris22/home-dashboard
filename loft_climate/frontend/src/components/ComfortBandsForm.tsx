import { useEffect, useState } from "react";

import { api } from "../api/client";
import { useConfig } from "../api/hooks";
import { ZONE_IDS, type ZoneId } from "../api/types";
import { Card } from "./glass/Card";

type ZoneCfg = {
  comfort_min: number;
  comfort_max: number;
  blind_group: string | null;
  stack_vent_delta_c?: number | null;
  bedtime_target_c?: number | null;
  bedtime_prep_minutes?: number | null;
};

type ConfigShape = {
  zones: Record<string, ZoneCfg>;
  schedule: { bedtime_local: string; wake_local: string };
  [k: string]: unknown;
};

const ZONE_LABEL: Record<ZoneId, string> = {
  mezzanine: "Mezzanine",
  downstairs: "Downstairs",
  ceiling_apex: "Ceiling apex",
  bedroom: "Bedroom",
};

export function ComfortBandsForm() {
  const { data, mutate } = useConfig();
  const [draft, setDraft] = useState<ConfigShape | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  useEffect(() => {
    if (data) setDraft(JSON.parse(JSON.stringify(data)) as ConfigShape);
  }, [data]);

  if (!draft) {
    return (
      <Card>
        <p className="opacity-70 text-sm">Loading config…</p>
      </Card>
    );
  }

  const updateZone = (zone: ZoneId, field: keyof ZoneCfg, value: number | null) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = { ...prev, zones: { ...prev.zones, [zone]: { ...prev.zones[zone] } } };
      // @ts-expect-error - dynamic field assignment is fine here
      next.zones[zone][field] = value as never;
      return next;
    });
  };

  const updateSchedule = (field: "bedtime_local" | "wake_local", value: string) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, schedule: { ...prev.schedule, [field]: value } };
    });
  };

  const save = async () => {
    if (!draft) return;
    setFeedback(null);
    setSaving(true);
    try {
      await api.put("/api/config", draft);
      await mutate();
      setFeedback({ kind: "ok", msg: "Saved." });
    } catch (e: unknown) {
      const detail = (e as { detail?: { detail?: unknown } })?.detail?.detail;
      let msg = "Save failed.";
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { loc?: string[]; msg?: string };
        msg = `${first.loc?.join(".") ?? ""}: ${first.msg ?? "invalid"}`;
      } else if (typeof detail === "string") {
        msg = detail;
      }
      setFeedback({ kind: "err", msg });
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (data) setDraft(JSON.parse(JSON.stringify(data)) as ConfigShape);
    setFeedback(null);
  };

  return (
    <Card>
      <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Comfort bands</h2>
      <p className="text-xs opacity-60 mb-4">
        Temperature range each zone should sit inside. Outside the band the engine
        starts firing rules. Bedroom uses an extra "bedtime target" reached by
        bedtime.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {ZONE_IDS.map((z) => {
          const zc = draft.zones[z];
          if (!zc) return null;
          return (
            <fieldset key={z} className="glass p-4 space-y-3">
              <legend className="text-sm font-medium">{ZONE_LABEL[z]}</legend>
              <label className="flex justify-between items-center gap-3 text-sm">
                <span className="opacity-70 w-28">Min °C</span>
                <input
                  type="number"
                  step="0.5"
                  value={zc.comfort_min}
                  onChange={(e) => updateZone(z, "comfort_min", parseFloat(e.target.value))}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums"
                />
              </label>
              <label className="flex justify-between items-center gap-3 text-sm">
                <span className="opacity-70 w-28">Max °C</span>
                <input
                  type="number"
                  step="0.5"
                  value={zc.comfort_max}
                  onChange={(e) => updateZone(z, "comfort_max", parseFloat(e.target.value))}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums"
                />
              </label>
              {z === "bedroom" && (
                <>
                  <label className="flex justify-between items-center gap-3 text-sm">
                    <span className="opacity-70 w-28">Bedtime target °C</span>
                    <input
                      type="number"
                      step="0.5"
                      value={zc.bedtime_target_c ?? ""}
                      onChange={(e) =>
                        updateZone(
                          z,
                          "bedtime_target_c",
                          e.target.value === "" ? null : parseFloat(e.target.value),
                        )
                      }
                      className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums"
                    />
                  </label>
                  <label className="flex justify-between items-center gap-3 text-sm">
                    <span className="opacity-70 w-28">Pre-cool window</span>
                    <input
                      type="number"
                      step="5"
                      value={zc.bedtime_prep_minutes ?? ""}
                      onChange={(e) =>
                        updateZone(
                          z,
                          "bedtime_prep_minutes",
                          e.target.value === "" ? null : parseInt(e.target.value, 10),
                        )
                      }
                      className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums"
                    />
                    <span className="text-xs opacity-50 w-12 text-right">min</span>
                  </label>
                </>
              )}
              {z === "ceiling_apex" && (
                <label className="flex justify-between items-center gap-3 text-sm">
                  <span className="opacity-70 w-28">Stack-vent Δ°C</span>
                  <input
                    type="number"
                    step="0.5"
                    value={zc.stack_vent_delta_c ?? ""}
                    onChange={(e) =>
                      updateZone(
                        z,
                        "stack_vent_delta_c",
                        e.target.value === "" ? null : parseFloat(e.target.value),
                      )
                    }
                    className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums"
                  />
                </label>
              )}
            </fieldset>
          );
        })}
      </div>

      <fieldset className="glass p-4 space-y-3 mt-4">
        <legend className="text-sm font-medium">Schedule</legend>
        <label className="flex justify-between items-center gap-3 text-sm">
          <span className="opacity-70 w-28">Bedtime</span>
          <input
            type="time"
            value={draft.schedule.bedtime_local}
            onChange={(e) => updateSchedule("bedtime_local", e.target.value)}
            className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1"
          />
        </label>
        <label className="flex justify-between items-center gap-3 text-sm">
          <span className="opacity-70 w-28">Wake</span>
          <input
            type="time"
            value={draft.schedule.wake_local}
            onChange={(e) => updateSchedule("wake_local", e.target.value)}
            className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1"
          />
        </label>
      </fieldset>

      <div className="flex items-center gap-3 mt-4">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="glass-strong px-4 py-2 hover:bg-white/15 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save comfort bands"}
        </button>
        <button
          type="button"
          onClick={reset}
          className="px-3 py-2 opacity-70 hover:opacity-100 text-sm"
        >
          Reset
        </button>
        {feedback && (
          <span
            className={`text-sm ${
              feedback.kind === "ok" ? "text-emerald-300" : "text-rose-300"
            }`}
          >
            {feedback.msg}
          </span>
        )}
      </div>
    </Card>
  );
}
