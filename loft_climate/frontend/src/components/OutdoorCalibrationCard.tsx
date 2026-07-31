import { useState } from "react";
import useSWR from "swr";

import { api, fetcher } from "../api/client";
import { Card } from "../_shared/Card";

type BiasResponse = {
  calibration: {
    fitted_at: string;
    days_window: number;
    bias_by_hour: number[];
    sample_counts: number[];
  } | null;
  settings: {
    correction: "sensor_only" | "sensor_bias_corrected";
    microclimate_baseline_c: number;
    clearness_floor: number;
    fit_window_days: number;
    fit_interval_days: number;
  };
  note?: string;
};

function formatFittedAt(iso: string): string {
  const d = new Date(iso);
  const rel = Math.round((Date.now() - d.getTime()) / (60 * 60 * 1000));
  if (rel < 1) return "just now";
  if (rel < 24) return `${rel}h ago`;
  return `${Math.floor(rel / 24)}d ago`;
}

export function OutdoorCalibrationCard() {
  const { data, error, mutate } = useSWR<BiasResponse>("/api/outdoor/bias", fetcher);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const recalibrate = async () => {
    setMsg(null);
    setBusy(true);
    try {
      const resp = await api.post<BiasResponse>("/api/outdoor/bias");
      // Force a fresh GET rather than substituting the POST response
      // directly — even though POST now returns the same envelope, this
      // stays correct if a future POST ever returns a partial payload.
      await mutate();
      setMsg(
        resp.calibration
          ? { kind: "ok", text: "Refit complete." }
          : { kind: "ok", text: resp.note || "Not enough history yet." },
      );
    } catch (e) {
      const detail = (e as { detail?: { detail?: string } })?.detail?.detail;
      setMsg({ kind: "err", text: detail || "Recalibrate failed." });
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <Card>
        <h2 className="hud-label mb-2">Outdoor sensor calibration</h2>
        <p className="text-xs text-secondary">Could not load /api/outdoor/bias.</p>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <h2 className="hud-label mb-2">Outdoor sensor calibration</h2>
        <p className="text-xs text-secondary">Loading…</p>
      </Card>
    );
  }

  const cal = data.calibration;
  const bias = cal?.bias_by_hour ?? [];
  const counts = cal?.sample_counts ?? [];
  // Defensive default. If a future POST ever returns a payload without
  // settings and we forget to guard downstream, this stops the whole page
  // blanking on a render exception.
  const settings = data.settings ?? {
    correction: "sensor_bias_corrected" as const,
    microclimate_baseline_c: 1.5,
    clearness_floor: 0.15,
    fit_window_days: 30,
    fit_interval_days: 7,
  };

  // Scale bars to the shared max magnitude so positive and negative
  // biases share a visual axis. Baseline reference line at
  // microclimate_baseline_c helps the user see what's being subtracted.
  const maxMag = Math.max(1, ...bias.map((v) => Math.abs(v)));
  const barH = 60; // px

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="hud-label">Outdoor sensor calibration</h2>
        <span className="text-xs text-secondary">
          {settings.correction === "sensor_bias_corrected"
            ? "Bias correction on"
            : "Raw sensor only"}
        </span>
      </div>

      {!cal ? (
        <p className="text-xs text-secondary">
          No calibration fitted yet. The scheduler runs on the first slow tick;
          if that hasn't completed, tap Recalibrate to force one.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <p className="text-secondary">Fitted</p>
              <p className="text-primary font-bold text-sm">
                {formatFittedAt(cal.fitted_at)}
              </p>
            </div>
            <div>
              <p className="text-secondary">Window</p>
              <p className="text-primary font-bold text-sm">
                {cal.days_window}d
              </p>
            </div>
            <div>
              <p className="text-secondary">Peak bias</p>
              <p className="text-primary font-bold text-sm">
                +{Math.max(...bias).toFixed(1)}°C
                <span className="text-secondary font-normal ml-1">
                  @ {String(bias.indexOf(Math.max(...bias))).padStart(2, "0")}:00
                </span>
              </p>
            </div>
          </div>

          <div>
            <div className="flex items-end gap-[2px] h-[60px] border-b border-secondary/30 relative">
              {/* Baseline reference line — anything above this gets subtracted. */}
              <div
                className="absolute left-0 right-0 border-t border-dashed border-secondary/50"
                style={{
                  bottom: `${(settings.microclimate_baseline_c / maxMag) * barH}px`,
                }}
                aria-hidden="true"
              />
              {bias.map((v, h) => {
                const heightPct = (Math.abs(v) / maxMag) * 100;
                const isPositive = v >= 0;
                const undersampled = (counts[h] ?? 0) < 3;
                return (
                  <div
                    key={h}
                    className="flex-1 flex flex-col justify-end min-w-0"
                    title={`${String(h).padStart(2, "0")}:00 — ${v >= 0 ? "+" : ""}${v.toFixed(2)}°C (n=${counts[h] ?? 0})`}
                  >
                    <div
                      className={
                        undersampled
                          ? "bg-secondary/30"
                          : isPositive
                            ? "bg-primary/70"
                            : "bg-tertiary/60"
                      }
                      style={{ height: `${heightPct}%` }}
                    />
                  </div>
                );
              })}
            </div>
            <div className="flex justify-between text-[10px] text-secondary mt-1 uppercase tracking-label">
              <span>00</span>
              <span>06</span>
              <span>12</span>
              <span>18</span>
              <span>23</span>
            </div>
            <p className="text-[10px] text-secondary mt-1">
              Dashed line = microclimate baseline ({settings.microclimate_baseline_c}°C).
              Bias above this is stripped from the sensor reading, scaled by cloud cover
              (min {Math.round(settings.clearness_floor * 100)}% on overcast).
              Faded bars have &lt;3 samples — treat with caution.
            </p>
          </div>
        </>
      )}

      <div className="flex items-center gap-3 pt-2 border-t border-secondary/30">
        <button
          type="button"
          onClick={recalibrate}
          disabled={busy}
          className="hud-button-primary disabled:opacity-50"
        >
          {busy ? "Recalibrating…" : "Recalibrate now"}
        </button>
        {msg && (
          <span
            className={`text-xs uppercase tracking-label font-bold ${
              msg.kind === "ok" ? "text-primary" : "text-tertiary"
            }`}
          >
            {msg.text}
          </span>
        )}
        <span className="text-xs text-secondary ml-auto">
          auto-refits every {settings.fit_interval_days}d
        </span>
      </div>
    </Card>
  );
}
