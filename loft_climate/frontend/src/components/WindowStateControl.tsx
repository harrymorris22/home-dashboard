/**
 * WindowStateControl — manual window state input.
 *
 * Why this exists (v0.12.0): casement windows have no HA integration at all
 * (no contact sensor, no smart actuator). Until now, current_state.windows
 * was always empty, so the dashboard couldn't show "currently open/closed"
 * annotations for windows and red-urgency window pushes kept re-firing
 * every 30 min even after the user acted. This is the windows analogue of
 * v0.9.0's BlindStateControl.
 *
 * POST goes to /api/windows/state which writes ActuatorState rows with
 * source="manual". DbCachedActuatorStateSource picks them up on the next
 * snapshot; per-zone window phrases in ActionPanel gain "(currently
 * open/closed)" / "✓ already" annotations; push triggers can suppress
 * repeats once state matches the recommendation.
 */
import { useState } from "react";

import { api } from "../api/client";
import { useDashboardState } from "../api/hooks";
import { ZONE_IDS, type ZoneId } from "../api/types";
import { Card } from "../_shared/Card";

const ZONE_LABEL: Record<ZoneId, string> = {
  mezzanine: "Office",
  downstairs: "Downstairs",
  ceiling_apex: "Ceiling apex",
  bedroom: "Bedroom",
};

type SetBody = Partial<Record<ZoneId, boolean>>;

export function WindowStateControl() {
  const { data, mutate } = useDashboardState();
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const currentWindows = data?.current_state?.windows ?? {};

  const send = async (body: SetBody, label: string) => {
    setBusy(true);
    setFeedback(null);
    try {
      await api.post("/api/windows/state", body);
      await mutate();
      setFeedback({ kind: "ok", msg: `${label} set` });
    } catch (e) {
      const detail = (e as { detail?: { detail?: unknown } })?.detail?.detail;
      const msg = typeof detail === "string" ? detail : "Save failed.";
      setFeedback({ kind: "err", msg });
    } finally {
      setBusy(false);
    }
  };

  const setAll = (isOpen: boolean) => {
    const body: SetBody = {};
    for (const z of ZONE_IDS) body[z] = isOpen;
    send(body, isOpen ? "All open" : "All closed");
  };

  const setOne = (z: ZoneId, isOpen: boolean) =>
    send({ [z]: isOpen }, `${ZONE_LABEL[z]} ${isOpen ? "open" : "closed"}`);

  const stateWord = (z: ZoneId): string => {
    const v = currentWindows[z];
    if (v === undefined) return "unknown";
    return v ? "open" : "closed";
  };

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="hud-label">Window state — set manually</span>
        {feedback && (
          <span
            className={`text-xs uppercase tracking-label font-bold ${
              feedback.kind === "ok" ? "text-primary" : "text-tertiary"
            }`}
          >
            {feedback.msg}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="hud-label w-20">All:</span>
        <button
          type="button"
          onClick={() => setAll(true)}
          disabled={busy}
          className="hud-button-secondary disabled:opacity-50"
        >
          All open
        </button>
        <button
          type="button"
          onClick={() => setAll(false)}
          disabled={busy}
          className="hud-button-secondary disabled:opacity-50"
        >
          All closed
        </button>
      </div>

      <ul className="space-y-2 border-t border-secondary/30 pt-3">
        {ZONE_IDS.map((z) => {
          const current = stateWord(z);
          return (
            <li key={z} className="flex flex-wrap items-center gap-2">
              <span className="text-secondary w-20">{ZONE_LABEL[z]}:</span>
              <button
                type="button"
                onClick={() => setOne(z, true)}
                disabled={busy}
                className="hud-button-secondary disabled:opacity-50"
              >
                Open
              </button>
              <button
                type="button"
                onClick={() => setOne(z, false)}
                disabled={busy}
                className="hud-button-secondary disabled:opacity-50"
              >
                Closed
              </button>
              <span className="text-xs text-secondary ml-auto">
                currently {current}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="text-xs text-secondary">
        Casement windows aren't on HA. Mark them here when you open or close
        one so the engine knows what's actually open.
      </p>
    </Card>
  );
}
