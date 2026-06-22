import { Card } from "../../_shared/Card";
import { urgencyText } from "../../_shared/urgency";
import { formatTemp } from "../../_shared/format";
import { useClimate } from "../../api/hooks";
import { LastUpdated } from "../../components/LastUpdated";
import { StaleBadge } from "../../components/StaleBadge";

// Both windows (zone-keyed) and blinds (group-keyed) render with the same
// user-facing names. Upstream uses divergent keys: zones={mezzanine, downstairs,
// bedroom, ceiling_apex}, blind groups={mezz, downstairs, bedroom}. Map both
// dialects to one user vocabulary.
const ZONE_LABEL: Record<string, string> = {
  mezzanine: "office",
  mezz: "office",
  downstairs: "downstairs",
  bedroom: "bedroom",
  ceiling_apex: "apex",
};
const label = (key: string) => ZONE_LABEL[key] ?? key;

/** Climate tile. Tap opens the full loft.harrymorris.me PWA in a new tab
 * — no UI duplication. Detail route exists as a safety net for deep links. */
export function ClimateTile() {
  const { data, error, isLoading } = useClimate();

  const onClick = () => {
    window.open("https://loft.harrymorris.me/", "_blank", "noopener");
  };

  if (isLoading) {
    return (
      <Card>
        <h2 className="hud-label">Climate</h2>
        <p className="text-secondary text-sm mt-3">Loading…</p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <h2 className="hud-label">Climate</h2>
        <p className="text-secondary text-sm mt-3" data-testid="climate-error">
          Climate offline
        </p>
      </Card>
    );
  }

  const windowLine = data.window_actions?.length
    ? data.window_actions
        .map((a) => `${a.action === "open" ? "Open" : "Close"} ${label(a.zone)}`)
        .join(" · ")
    : null;

  const blindLine = data.blind_actions?.length
    ? data.blind_actions
        .map(
          (a) =>
            `${a.direction === "raise" ? "Raise" : "Lower"} ${label(a.group)} blinds to ${a.target_pct}%`,
        )
        .join(" · ")
    : null;

  return (
    <Card
      onClick={onClick}
      className="cursor-pointer hover:border-primary transition flex flex-col gap-2"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      data-testid="climate-tile"
    >
      <div className="flex items-center justify-between">
        <h2 className="hud-label">Climate</h2>
        <div className="flex items-center gap-2">
          {data.stale && <StaleBadge />}
          <LastUpdated ts={data.last_success_at} />
        </div>
      </div>
      <div className={`font-display text-2xl uppercase tracking-tight ${urgencyText[data.urgency]}`}>
        {data.scenario.replaceAll("_", " ")}
      </div>
      <p className="text-sm text-secondary">
        Office <span className="text-primary font-bold">{formatTemp(data.office_temp_c)}</span>
      </p>
      {windowLine && (
        <p
          className="text-sm text-primary line-clamp-2"
          data-testid="climate-window-actions"
        >
          {windowLine}
        </p>
      )}
      {blindLine && (
        <p
          className="text-sm text-primary line-clamp-2"
          data-testid="climate-blind-actions"
        >
          {blindLine}
        </p>
      )}
      {data.prompt && <p className="text-xs text-secondary line-clamp-2">{data.prompt}</p>}
    </Card>
  );
}
