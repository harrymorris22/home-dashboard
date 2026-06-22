import { Card } from "../../_shared/Card";
import { ApiError } from "../../api/client";
import { useOura } from "../../api/hooks";
import { LastUpdated } from "../../components/LastUpdated";
import { StaleBadge } from "../../components/StaleBadge";

const fmt = (n: number) => n.toLocaleString("en-GB");
// `n ?? '—'` preserves the literal 0 (early-morning state); `n || '—'` would
// silently turn 0 into a dash, the most likely-to-ship-broken bug here.
const renderCount = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : fmt(n);

/** Oura step-count tile. Read-only (no detail page). */
export function OuraTile() {
  const { data, error, isLoading } = useOura();

  if (isLoading) {
    return (
      <Card>
        <h2 className="hud-label">Steps</h2>
        <p className="text-secondary text-sm mt-3">Loading…</p>
      </Card>
    );
  }

  if (error) {
    const apiErr = error as ApiError;
    const detail = (apiErr.detail as { error?: string; instruction?: string }) || {};
    if (apiErr.status === 503 && detail.error === "oura_pat_token_not_configured") {
      return (
        <Card>
          <h2 className="hud-label">Steps</h2>
          <p className="text-secondary text-sm mt-3" data-testid="oura-unconfigured">
            {detail.instruction || "Set oura_pat_token in Add-on options."}
          </p>
        </Card>
      );
    }
    if (apiErr.status === 503 && detail.error === "oura_token_invalid") {
      return (
        <Card>
          <h2 className="hud-label">Steps</h2>
          <p className="text-secondary text-sm mt-3" data-testid="oura-token-invalid">
            {detail.instruction || "PAT rejected by Oura. Re-create the token."}
          </p>
        </Card>
      );
    }
    return (
      <Card>
        <h2 className="hud-label">Steps</h2>
        <p className="text-secondary text-sm mt-3" data-testid="oura-error">
          Steps unavailable
        </p>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <h2 className="hud-label">Steps</h2>
        <p className="text-secondary text-sm mt-3" data-testid="oura-error">
          Steps unavailable
        </p>
      </Card>
    );
  }

  const today = data.step_count;
  const yesterday = data.step_count_yesterday;
  const bothNull =
    (today === null || today === undefined) && (yesterday === null || yesterday === undefined);
  const todayMissingYesterdayPresent =
    (today === null || today === undefined) && yesterday !== null && yesterday !== undefined;

  let subtitle: string;
  if (bothNull) {
    subtitle = "No step data yet";
  } else if (todayMissingYesterdayPresent) {
    subtitle = `yesterday ${fmt(yesterday as number)} · syncing today`;
  } else {
    subtitle = `yesterday ${renderCount(yesterday)}`;
  }

  return (
    <Card className="flex flex-col gap-2" data-testid="oura-tile">
      <div className="flex items-center justify-between">
        <h2 className="hud-label">Steps</h2>
        <div className="flex items-center gap-2">
          {data.stale && <StaleBadge />}
          <LastUpdated ts={data.last_success_at} />
        </div>
      </div>
      <div className="font-display text-3xl text-primary">{renderCount(today)}</div>
      <div className="text-sm text-secondary">{subtitle}</div>
    </Card>
  );
}
