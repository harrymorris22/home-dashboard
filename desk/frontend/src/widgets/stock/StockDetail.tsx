import { Card } from "../../_shared/Card";
import { formatPercent, formatPrice } from "../../_shared/format";
import { useStock } from "../../api/hooks";
import { StaleBadge } from "../../components/StaleBadge";
import { Sparkline } from "./Sparkline";

/** Stock detail: bigger chart + full numeric breakdown.
 * v1 keeps the 7-day sparkline; longer-range charts (1m/3m/1y) deferred —
 * they need a separate yfinance call with different period+interval and a
 * client-side period switcher. Worth doing once a real need appears. */
export function StockDetail({ ticker = "LQQ3.L" }: { ticker?: string }) {
  const { data, error, isLoading } = useStock(ticker);

  if (isLoading) {
    return (
      <Card>
        <p className="text-secondary">Loading {ticker}…</p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <p className="text-secondary">Stock data unavailable.</p>
      </Card>
    );
  }

  const up = data.day_change_pct >= 0;
  const sign = up ? "+" : "";

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-3xl uppercase tracking-tight text-primary">{data.ticker}</h1>
        {data.stale && <StaleBadge />}
      </div>

      <div className="hud-display text-primary">{formatPrice(data.price, data.currency)}</div>
      <div className="text-lg text-primary">
        <span className="font-bold">{sign}{formatPrice(data.day_change_abs, data.currency)}</span>
        <span className="text-secondary"> · </span>
        <span className="font-bold">{sign}{formatPercent(data.day_change_pct, 2)}</span>
        <span className="text-secondary"> today</span>
      </div>

      <div className="border-t border-secondary/30 pt-4">
        <h2 className="hud-label mb-2">7-day movement</h2>
        <Sparkline values={data.sparkline} width={600} height={120} strokeWidth={2} />
      </div>

      {data.last_success_at && (
        <p className="text-xs text-secondary">
          Last update: {new Date(data.last_success_at).toLocaleString()}
        </p>
      )}
    </Card>
  );
}
