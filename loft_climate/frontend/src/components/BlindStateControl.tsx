/**
 * BlindStateControl — manual blind state input.
 *
 * Why this exists (v0.9.0): Tahoma open/close-only blinds accept commands
 * but never report state back to HA. cover entities sit at state=unknown,
 * our HA cover source skips them, and the dashboard loses the "currently
 * up/down" annotation. Until the user gets position-reporting blinds, this
 * lets them mark state from the dashboard whenever they operate a blind.
 *
 * POST goes to /api/blinds/state which writes ActuatorState rows with
 * source="manual". DbCachedActuatorStateSource picks them up on the next
 * snapshot, the "Blind state unknown" banner clears, and per-zone rows
 * gain the "(currently up/down)" / "✓ already" annotations.
 */
import { useState } from "react";

import { api } from "../api/client";
import { useDashboardState } from "../api/hooks";
import { BLIND_GROUP_IDS, type BlindGroupId } from "../api/types";
import { Card } from "../_shared/Card";

const GROUP_LABEL: Record<BlindGroupId, string> = {
  mezz: "Office",
  downstairs: "Downstairs",
  bedroom: "Bedroom",
};

type SetBody = Partial<Record<BlindGroupId, 0 | 100>>;

export function BlindStateControl() {
  const { data, mutate } = useDashboardState();
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const currentBlinds = data?.current_state?.blinds ?? {};

  const send = async (body: SetBody, label: string) => {
    setBusy(true);
    setFeedback(null);
    try {
      await api.post("/api/blinds/state", body);
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

  const setAll = (pct: 0 | 100) => {
    const body: SetBody = {};
    for (const g of BLIND_GROUP_IDS) body[g] = pct;
    send(body, pct === 0 ? "All up" : "All down");
  };

  const setOne = (g: BlindGroupId, pct: 0 | 100) =>
    send({ [g]: pct }, `${GROUP_LABEL[g]} ${pct === 0 ? "up" : "down"}`);

  const stateWord = (g: BlindGroupId): string => {
    const v = currentBlinds[g];
    if (v === undefined) return "unknown";
    if (v <= 25) return "up";
    if (v >= 75) return "down";
    return `${v}%`;
  };

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="hud-label">Blind state — set manually</span>
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
          onClick={() => setAll(0)}
          disabled={busy}
          className="hud-button-secondary disabled:opacity-50"
        >
          All up
        </button>
        <button
          type="button"
          onClick={() => setAll(100)}
          disabled={busy}
          className="hud-button-secondary disabled:opacity-50"
        >
          All down
        </button>
      </div>

      <ul className="space-y-2 border-t border-secondary/30 pt-3">
        {BLIND_GROUP_IDS.map((g) => {
          const current = stateWord(g);
          return (
            <li key={g} className="flex flex-wrap items-center gap-2">
              <span className="text-secondary w-20">{GROUP_LABEL[g]}:</span>
              <button
                type="button"
                onClick={() => setOne(g, 0)}
                disabled={busy}
                className="hud-button-secondary disabled:opacity-50"
              >
                Up
              </button>
              <button
                type="button"
                onClick={() => setOne(g, 100)}
                disabled={busy}
                className="hud-button-secondary disabled:opacity-50"
              >
                Down
              </button>
              <span className="text-xs text-secondary ml-auto">
                currently {current}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="text-xs text-secondary">
        Tahoma open/close-only blinds don't report state back. Mark them here
        when you operate them so the engine can compare "should be" vs
        "is" correctly.
      </p>
    </Card>
  );
}
