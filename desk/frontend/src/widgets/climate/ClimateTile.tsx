import { Card } from "../../_shared/Card";
import { urgencyText } from "../../_shared/urgency";
import { formatTemp } from "../../_shared/format";
import { useClimate } from "../../api/hooks";
import { StaleBadge } from "../../components/StaleBadge";

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
        {data.stale && <StaleBadge />}
      </div>
      <div className={`font-display text-2xl uppercase tracking-tight ${urgencyText[data.urgency]}`}>
        {data.scenario.replaceAll("_", " ")}
      </div>
      <p className="text-sm text-secondary">
        Bedroom <span className="text-primary font-bold">{formatTemp(data.bedroom_temp_c)}</span>
      </p>
      {data.prompt && <p className="text-xs text-secondary line-clamp-2">{data.prompt}</p>}
    </Card>
  );
}
