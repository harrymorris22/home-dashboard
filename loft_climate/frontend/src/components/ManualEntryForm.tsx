import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import {
  useDashboardState,
  useLatestReadings,
  useLatestSunshine,
  useSunshineScale,
} from "../api/hooks";
import { BLIND_GROUP_IDS, type BlindGroupId, ZONE_IDS, type ZoneId } from "../api/types";
import { Card } from "./glass/Card";

const ZONE_LABEL: Record<ZoneId, string> = {
  mezzanine: "Mezzanine",
  downstairs: "Downstairs",
  ceiling_apex: "Ceiling apex",
  bedroom: "Bedroom",
};

const BLIND_LABEL: Record<BlindGroupId, string> = {
  mezz: "Mezzanine",
  downstairs: "Downstairs",
  bedroom: "Bedroom",
};

const BLIND_STEPS = [0, 25, 50, 75, 100] as const;

type ZoneFields = { temp_c: string; humidity_pct: string };

const empty = (): ZoneFields => ({ temp_c: "", humidity_pct: "" });

export function ManualEntryForm() {
  const { data: latest, mutate: mutateLatest } = useLatestReadings();
  const { data: sunshineLatest, mutate: mutateSun } = useLatestSunshine();
  const { data: scale } = useSunshineScale();
  const { data: state, mutate: mutateState } = useDashboardState();
  const navigate = useNavigate();

  const [zones, setZones] = useState<Record<ZoneId, ZoneFields>>({
    mezzanine: empty(),
    downstairs: empty(),
    ceiling_apex: empty(),
    bedroom: empty(),
  });
  const [sunshineStep, setSunshineStep] = useState<number | null>(null);
  const [blindState, setBlindState] = useState<Record<BlindGroupId, number | null>>({
    mezz: null,
    downstairs: null,
    bedroom: null,
  });
  const [windowState, setWindowState] = useState<Record<ZoneId, boolean | null>>({
    mezzanine: null,
    downstairs: null,
    ceiling_apex: null,
    bedroom: null,
  });
  const [feedback, setFeedback] = useState({ action_taken: "", felt_right: "", note: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const knownBlind = (g: BlindGroupId): number | null =>
    state?.current_state?.blinds?.[g] ?? null;
  const knownWindow = (z: ZoneId): boolean | null =>
    state?.current_state?.windows?.[z] ?? null;

  const placeholderFor = (zone: ZoneId, field: keyof ZoneFields): string => {
    const last = latest?.zones[zone];
    if (!last) return "";
    const v = field === "temp_c" ? last.temp_c : last.humidity_pct;
    return v == null ? "" : String(v);
  };

  const lastSunshineLabel = (): string | null => {
    const s = sunshineLatest?.sunshine;
    if (!s || !scale) return null;
    if (s.scale != null) {
      const item = scale.items.find((i) => i.step === s.scale);
      return item ? `${item.label} (${item.lux} lx)` : `${s.lux} lx`;
    }
    return `${s.lux} lx`;
  };

  const updateZone = (zone: ZoneId, field: keyof ZoneFields, value: string) =>
    setZones((prev) => ({ ...prev, [zone]: { ...prev[zone], [field]: value } }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const payload: {
      zones: Record<string, { temp_c: number; humidity_pct: number | null }>;
      feedback?: { action_taken?: string; felt_right?: string; note?: string };
      sunshine?: { scale: number };
    } = { zones: {} };
    for (const z of ZONE_IDS) {
      const fields = zones[z];
      const t = parseFloat(fields.temp_c);
      if (Number.isNaN(t)) {
        setError(`Temperature is required for ${ZONE_LABEL[z]}.`);
        return;
      }
      payload.zones[z] = {
        temp_c: t,
        humidity_pct: fields.humidity_pct === "" ? null : parseFloat(fields.humidity_pct),
      };
    }
    if (sunshineStep !== null) {
      payload.sunshine = { scale: sunshineStep };
    }
    const blinds: Record<string, number> = {};
    for (const g of BLIND_GROUP_IDS) {
      if (blindState[g] !== null) blinds[g] = blindState[g] as number;
    }
    const windows: Record<string, boolean> = {};
    for (const z of ZONE_IDS) {
      if (windowState[z] !== null) windows[z] = windowState[z] as boolean;
    }
    if (Object.keys(blinds).length || Object.keys(windows).length) {
      (payload as any).current_state = { blinds, windows };
    }
    if (feedback.action_taken || feedback.felt_right || feedback.note) {
      payload.feedback = {
        action_taken: feedback.action_taken || undefined,
        felt_right: feedback.felt_right || undefined,
        note: feedback.note || undefined,
      };
    }
    setSubmitting(true);
    try {
      await api.post("/api/readings", payload);
      await Promise.all([mutateLatest(), mutateSun(), mutateState()]);
      navigate("/");
    } catch (err: unknown) {
      const e = err as { status?: number };
      setError(`Submit failed (status ${e.status ?? "?"}).`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Card>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-sm uppercase tracking-wider opacity-70">Sunshine on SW glazing</h2>
          {lastSunshineLabel() && (
            <span className="text-xs opacity-60">last: {lastSunshineLabel()}</span>
          )}
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {(scale?.items ?? []).map((item) => {
            const selected = sunshineStep === item.step;
            return (
              <button
                key={item.step}
                type="button"
                onClick={() => setSunshineStep(selected ? null : item.step)}
                className={`px-2 py-3 rounded-lg border text-xs flex flex-col items-center gap-1 transition ${
                  selected
                    ? "border-amber-300/70 bg-amber-300/10 text-amber-100"
                    : "border-white/10 hover:border-white/30"
                }`}
              >
                <span className="text-lg leading-none">{item.step}</span>
                <span className="text-center leading-tight">{item.label}</span>
                <span className="opacity-50">~{item.lux} lx</span>
              </button>
            );
          })}
        </div>
        <p className="text-xs opacity-60 mt-2">
          Phase 2: replaced by the Aqara Light Sensor T1 inside the SW window.
        </p>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Zone temps</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ZONE_IDS.map((z) => (
            <fieldset key={z} className="glass p-4 space-y-2">
              <legend className="text-sm font-medium">{ZONE_LABEL[z]}</legend>
              <label className="flex justify-between items-center gap-3 text-sm">
                <span className="opacity-70 w-20">Temp °C</span>
                <input
                  type="number"
                  step="0.1"
                  required
                  value={zones[z].temp_c}
                  placeholder={placeholderFor(z, "temp_c")}
                  onChange={(e) => updateZone(z, "temp_c", e.target.value)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums placeholder:opacity-40"
                />
              </label>
              <label className="flex justify-between items-center gap-3 text-sm">
                <span className="opacity-70 w-20">RH %</span>
                <input
                  type="number"
                  step="1"
                  value={zones[z].humidity_pct}
                  placeholder={placeholderFor(z, "humidity_pct")}
                  onChange={(e) => updateZone(z, "humidity_pct", e.target.value)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 flex-1 text-right tabular-nums placeholder:opacity-40"
                />
              </label>
            </fieldset>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">
          Current configuration
        </h2>
        <p className="text-xs opacity-60 mb-4">
          Tell the engine what's actually open/closed right now so it knows what
          (if anything) needs to change. Phase 2: replaced by Home Assistant cover
          state.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <fieldset className="glass p-4 space-y-3">
            <legend className="text-sm font-medium">Blinds</legend>
            {BLIND_GROUP_IDS.map((g) => {
              const known = knownBlind(g);
              const selected = blindState[g];
              return (
                <div key={g} className="space-y-1">
                  <div className="flex items-baseline justify-between text-sm">
                    <span>{BLIND_LABEL[g]}</span>
                    {known !== null && (
                      <span className="text-xs opacity-50">last: {known}%</span>
                    )}
                  </div>
                  <div className="flex gap-1">
                    {BLIND_STEPS.map((step) => (
                      <button
                        key={step}
                        type="button"
                        onClick={() =>
                          setBlindState((p) => ({
                            ...p,
                            [g]: selected === step ? null : step,
                          }))
                        }
                        className={`flex-1 py-1.5 text-xs rounded border transition ${
                          selected === step
                            ? "border-emerald-300/70 bg-emerald-300/10 text-emerald-100"
                            : "border-white/10 hover:border-white/30"
                        }`}
                      >
                        {step === 0 ? "Up" : step === 100 ? "Down" : `${step}%`}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </fieldset>

          <fieldset className="glass p-4 space-y-3">
            <legend className="text-sm font-medium">Windows</legend>
            {ZONE_IDS.map((z) => {
              const known = knownWindow(z);
              const selected = windowState[z];
              return (
                <div key={z} className="space-y-1">
                  <div className="flex items-baseline justify-between text-sm">
                    <span>{ZONE_LABEL[z]}</span>
                    {known !== null && (
                      <span className="text-xs opacity-50">
                        last: {known ? "open" : "closed"}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-1">
                    {[
                      { v: false, label: "Closed" },
                      { v: true, label: "Open" },
                    ].map(({ v, label }) => (
                      <button
                        key={String(v)}
                        type="button"
                        onClick={() =>
                          setWindowState((p) => ({
                            ...p,
                            [z]: selected === v ? null : v,
                          }))
                        }
                        className={`flex-1 py-1.5 text-xs rounded border transition ${
                          selected === v
                            ? "border-emerald-300/70 bg-emerald-300/10 text-emerald-100"
                            : "border-white/10 hover:border-white/30"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </fieldset>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">
          Feedback (optional but helpful for tuning)
        </h2>
        <div className="space-y-3 text-sm">
          <label className="block">
            <span className="opacity-70 block mb-1">What did you actually do?</span>
            <input
              type="text"
              value={feedback.action_taken}
              onChange={(e) => setFeedback((p) => ({ ...p, action_taken: e.target.value }))}
              placeholder="e.g. closed bedroom blind, opened kitchen window"
              className="w-full bg-white/5 border border-white/10 rounded px-2 py-2"
            />
          </label>
          <label className="block">
            <span className="opacity-70 block mb-1">Did the recommendation feel right?</span>
            <select
              value={feedback.felt_right}
              onChange={(e) => setFeedback((p) => ({ ...p, felt_right: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded px-2 py-2"
            >
              <option value="">—</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
              <option value="unsure">Unsure</option>
            </select>
          </label>
          <label className="block">
            <span className="opacity-70 block mb-1">Note</span>
            <textarea
              value={feedback.note}
              onChange={(e) => setFeedback((p) => ({ ...p, note: e.target.value }))}
              rows={2}
              className="w-full bg-white/5 border border-white/10 rounded px-2 py-2"
            />
          </label>
        </div>
      </Card>

      {error && (
        <div className="glass border-rose-500/40 p-3 text-sm text-rose-300">{error}</div>
      )}

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="glass-strong px-5 py-3 font-medium hover:bg-white/15 disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save reading"}
        </button>
      </div>
    </form>
  );
}
