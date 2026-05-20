import { useNavigate } from "react-router-dom";

import { Card } from "../../_shared/Card";
import { formatPercent } from "../../_shared/format";
import { useSystem } from "../../api/hooks";

function formatTemp(t: number | null): string {
  if (t === null) return "—";
  return `${t.toFixed(0)}°C`;
}

/** System tile. CPU temp, disk %, internet uptime. */
export function SystemTile() {
  const navigate = useNavigate();
  const { data, error, isLoading } = useSystem();

  const onClick = () => navigate("/widget/system");

  if (isLoading) {
    return (
      <Card>
        <h2 className="hud-label">System</h2>
        <p className="text-secondary text-sm mt-3">Loading…</p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <h2 className="hud-label">System</h2>
        <p className="text-secondary text-sm mt-3" data-testid="system-error">
          System metrics unavailable
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
      data-testid="system-tile"
    >
      <h2 className="hud-label">System</h2>
      <div className="grid grid-cols-2 gap-1 text-sm">
        <span className="text-secondary">CPU temp</span>
        <span className="text-primary font-bold text-right">{formatTemp(data.cpu_temp_c)}</span>
        <span className="text-secondary">Disk</span>
        <span className="text-primary font-bold text-right">{formatPercent(data.disk_pct, 0)}</span>
        <span className="text-secondary">Internet 24h</span>
        <span className="text-primary font-bold text-right">
          {data.internet_24h_pct === null ? "—" : formatPercent(data.internet_24h_pct, 0)}
        </span>
      </div>
    </Card>
  );
}
