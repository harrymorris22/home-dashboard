import { Card } from "../../_shared/Card";
import { formatPercent } from "../../_shared/format";
import { useSystem } from "../../api/hooks";

function formatTemp(t: number | null): string {
  if (t === null) return "—";
  return `${t.toFixed(1)}°C`;
}

export function SystemDetail() {
  const { data, error, isLoading } = useSystem();

  if (isLoading) return <Card><p className="text-secondary">Loading…</p></Card>;
  if (error || !data) return <Card><p className="text-secondary">System metrics unavailable.</p></Card>;

  return (
    <Card className="flex flex-col gap-4">
      <h1 className="font-display text-3xl uppercase tracking-tight text-primary">System health</h1>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Metric label="CPU" value={formatPercent(data.cpu_pct, 0)} />
        <Metric label="CPU temp" value={formatTemp(data.cpu_temp_c)} />
        <Metric label="Memory" value={formatPercent(data.mem_pct, 0)} />
        <Metric label="Disk" value={formatPercent(data.disk_pct, 0)} />
      </div>

      <div className="border-t border-secondary/30 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Metric
          label="Internet 24h"
          value={data.internet_24h_pct === null ? "ping pending" : formatPercent(data.internet_24h_pct, 1)}
        />
        <Metric
          label="LAN 24h"
          value={data.lan_24h_pct === null ? "no LAN probe" : formatPercent(data.lan_24h_pct, 1)}
        />
      </div>

      {data.last_ping_ts && (
        <p className="text-xs text-secondary">
          Last ping: {new Date(data.last_ping_ts).toLocaleString()}
        </p>
      )}
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="hud-label mb-1">{label}</div>
      <div className="font-display text-2xl text-primary">{value}</div>
    </div>
  );
}
