import { useEffect, useState } from "react";
import useSWR from "swr";

import { fetcher } from "../api/client";
import { Card } from "../components/glass/Card";
import {
  disablePush,
  enablePush,
  getPushState,
  type PushDiagnostics,
  sendTest,
  snoozeUntil,
} from "../lib/push";

type StatusResp = {
  enabled: boolean;
  vapid_ready: boolean;
  vapid_subject: string | null;
  subscription_count: number;
  snooze_until: string | null;
};

type SubscriptionsResp = {
  items: {
    id: number;
    ua: string | null;
    label: string | null;
    created_at: string | null;
    last_success_at: string | null;
    last_error_at: string | null;
    failure_count: number;
  }[];
};

export function Notifications() {
  const [diag, setDiag] = useState<PushDiagnostics | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const { data: status, mutate: mutateStatus } = useSWR<StatusResp>(
    "/api/push/status",
    fetcher,
    { refreshInterval: 30_000 },
  );
  const { data: subs, mutate: mutateSubs } = useSWR<SubscriptionsResp>(
    "/api/push/subscriptions",
    fetcher,
    { refreshInterval: 30_000 },
  );

  useEffect(() => {
    void getPushState().then(setDiag);
  }, []);

  const refreshDiag = async () => setDiag(await getPushState());
  const safeRun = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setFeedback(null);
    try {
      await fn();
      await Promise.all([mutateStatus(), mutateSubs(), refreshDiag()]);
      setFeedback({ kind: "ok", msg: `${label} ok` });
    } catch (e) {
      setFeedback({ kind: "err", msg: `${label} failed: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  const onEnable = () => safeRun("Enable", enablePush);
  const onDisable = () => safeRun("Disable", disablePush);
  const onTest = () => safeRun("Test push", sendTest);
  const onResume = () => safeRun("Resume", () => snoozeUntil(null));
  const onSnoozeHours = (hours: number) =>
    safeRun(`Snooze ${hours}h`, () => snoozeUntil(new Date(Date.now() + hours * 3600_000)));
  const onSnoozeUntilMorning = () => {
    const target = new Date();
    target.setDate(target.getDate() + 1);
    target.setHours(7, 0, 0, 0);
    return safeRun("Snooze until 07:00", () => snoozeUntil(target));
  };

  const installed = diag?.installed === true;
  const showInstallCallout = !installed && /iPhone|iPad|iPod/.test(navigator.userAgent);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Notifications</h1>

      {showInstallCallout && (
        <Card className="border-amber-300/40 bg-amber-300/5">
          <p className="text-sm">
            <span className="font-medium text-amber-200">iPhone? Install first.</span>{" "}
            On iOS, push only works for installed PWAs. Tap the <b>Share</b> icon
            in Safari → <b>Add to Home Screen</b>, then open the dashboard from the
            new icon.
          </p>
        </Card>
      )}

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Diagnostics</h2>
        <ul className="text-sm space-y-1 opacity-90">
          <li>Installed PWA: <strong>{diag ? String(diag.installed) : "…"}</strong></li>
          <li>Permission: <strong>{diag?.permission ?? "…"}</strong></li>
          <li>Service Worker registered: <strong>{diag ? String(diag.swRegistered) : "…"}</strong></li>
          <li>Subscribed (this device): <strong>{diag ? String(diag.subscribed) : "…"}</strong></li>
          {status && (
            <>
              <li>VAPID ready (server): <strong>{String(status.vapid_ready)}</strong></li>
              <li>Notifications enabled (config): <strong>{String(status.enabled)}</strong></li>
              <li>Total subscriptions: <strong>{status.subscription_count}</strong></li>
              <li>
                Snoozed until:{" "}
                <strong>
                  {status.snooze_until ? new Date(status.snooze_until).toLocaleString() : "—"}
                </strong>
              </li>
            </>
          )}
        </ul>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">This device</h2>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onEnable}
            disabled={busy || diag?.subscribed}
            className="glass-strong px-4 py-2 hover:bg-white/15 disabled:opacity-50"
          >
            Enable notifications
          </button>
          <button
            type="button"
            onClick={onDisable}
            disabled={busy || !diag?.subscribed}
            className="glass px-4 py-2 hover:bg-white/15 disabled:opacity-50"
          >
            Disable
          </button>
          <button
            type="button"
            onClick={onTest}
            disabled={busy || !diag?.subscribed}
            className="glass px-4 py-2 hover:bg-white/15 disabled:opacity-50"
          >
            Send test push
          </button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Snooze</h2>
        <p className="text-xs opacity-60 mb-3">
          Suppress all pushes (including red) for a fixed window. Useful for
          travel or when you actively don't want pings.
        </p>
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={() => onSnoozeHours(2)} disabled={busy}
                  className="glass px-4 py-2 hover:bg-white/15 disabled:opacity-50">
            Snooze 2 h
          </button>
          <button type="button" onClick={onSnoozeUntilMorning} disabled={busy}
                  className="glass px-4 py-2 hover:bg-white/15 disabled:opacity-50">
            Snooze until 07:00
          </button>
          <button type="button" onClick={onResume} disabled={busy}
                  className="glass-strong px-4 py-2 hover:bg-white/15 disabled:opacity-50">
            Resume
          </button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Registered devices</h2>
        {!subs?.items?.length && (
          <p className="text-sm opacity-70">No devices subscribed yet.</p>
        )}
        <ul className="space-y-2">
          {subs?.items?.map((s) => (
            <li key={s.id} className="text-sm border-t border-white/10 pt-2">
              <div className="flex justify-between">
                <span>{s.label || s.ua || `Device #${s.id}`}</span>
                <span className="opacity-50 text-xs">
                  {s.last_success_at
                    ? `last ok ${new Date(s.last_success_at).toLocaleString()}`
                    : "never"}
                </span>
              </div>
              {s.failure_count > 0 && (
                <div className="text-xs text-rose-300 mt-1">
                  {s.failure_count} consecutive failures
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {feedback && (
        <div
          className={`glass p-3 text-sm ${
            feedback.kind === "ok" ? "text-emerald-300" : "text-rose-300"
          }`}
        >
          {feedback.msg}
        </div>
      )}
    </div>
  );
}
