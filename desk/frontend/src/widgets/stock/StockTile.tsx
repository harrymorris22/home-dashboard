import { useNavigate } from "react-router-dom";

import { Card } from "../../_shared/Card";
import { formatPercent, formatPrice } from "../../_shared/format";
import { useStock } from "../../api/hooks";
import { LastUpdated } from "../../components/LastUpdated";
import { StaleBadge } from "../../components/StaleBadge";
import { Sparkline } from "./Sparkline";

/** Stock tile. LQQ3.L by default. Tap → /widget/stock for charts. */
export function StockTile({ ticker = "LQQ3.L" }: { ticker?: string }) {
  const navigate = useNavigate();
  const { data, error, isLoading } = useStock(ticker);

  const onClick = () => navigate("/widget/stock");

  if (isLoading) {
    return (
      <Card>
        <h2 className="hud-label">Stock</h2>
        <p className="text-secondary text-sm mt-3">Loading…</p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <h2 className="hud-label">Stock</h2>
        <p className="text-secondary text-sm mt-3" data-testid="stock-error">
          Stock data unavailable
        </p>
      </Card>
    );
  }

  const up = data.day_change_pct >= 0;
  const sign = up ? "+" : "";

  return (
    <Card
      onClick={onClick}
      className="cursor-pointer hover:border-primary transition flex flex-col gap-2"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      data-testid="stock-tile"
    >
      <div className="flex items-center justify-between">
        <h2 className="hud-label">{data.ticker}</h2>
        <div className="flex items-center gap-2">
          {data.stale && <StaleBadge />}
          <LastUpdated ts={data.last_success_at} />
        </div>
      </div>
      <div className="font-display text-3xl text-primary">{formatPrice(data.price, data.currency)}</div>
      <div className="text-sm text-secondary">
        <span className={up ? "text-primary font-bold" : "text-primary font-bold"}>
          {sign}{formatPercent(data.day_change_pct, 2)}
        </span>{" "}
        today
      </div>
      <Sparkline values={data.sparkline} width={180} height={40} />
    </Card>
  );
}
