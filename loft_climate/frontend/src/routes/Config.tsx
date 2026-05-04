import { useEffect, useState } from "react";

import { api } from "../api/client";
import { useConfig } from "../api/hooks";
import { ComfortBandsForm } from "../components/ComfortBandsForm";
import { Card } from "../components/glass/Card";

export function Config() {
  const { data, error, mutate } = useConfig();
  const [text, setText] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  useEffect(() => {
    if (data) setText(JSON.stringify(data, null, 2));
  }, [data]);

  const save = async () => {
    setFeedback(null);
    setSaving(true);
    try {
      const parsed = JSON.parse(text);
      await api.put("/api/config", parsed);
      await mutate();
      setFeedback({ kind: "ok", msg: "Saved." });
    } catch (e: unknown) {
      const detail = (e as { detail?: { detail?: unknown } })?.detail?.detail;
      const msg =
        Array.isArray(detail)
          ? JSON.stringify(detail)
          : typeof detail === "object"
            ? JSON.stringify(detail)
            : (e as Error).message || "Save failed.";
      setFeedback({ kind: "err", msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Config</h1>

      {error && (
        <Card className="border-rose-500/40">
          <p className="text-rose-300">Could not load /api/config.</p>
        </Card>
      )}

      <ComfortBandsForm />

      <Card>
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className="text-sm uppercase tracking-wider opacity-70 hover:opacity-100"
        >
          {advancedOpen ? "▾" : "▸"} Advanced (raw JSON)
        </button>
        {advancedOpen && (
          <div className="mt-4">
            <p className="text-xs opacity-60 mb-3">
              Edits validation invariants on save (e.g.{" "}
              <code>comfort_min &lt; comfort_max</code>) — bad values are rejected with
              an error.
            </p>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              spellCheck={false}
              className="w-full font-mono text-xs bg-black/30 border border-white/10 rounded p-3 min-h-[480px]"
            />
            <div className="flex items-center gap-3 mt-3">
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="glass-strong px-4 py-2 hover:bg-white/15 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save raw JSON"}
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
          </div>
        )}
      </Card>
    </div>
  );
}
