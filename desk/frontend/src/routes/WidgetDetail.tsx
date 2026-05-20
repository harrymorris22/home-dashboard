import { useParams, Link } from "react-router-dom";

import { Card } from "../_shared/Card";
import { CalendarDetail } from "../widgets/calendar/CalendarDetail";
import { ClimateDetail } from "../widgets/climate/ClimateDetail";
import { StockDetail } from "../widgets/stock/StockDetail";
import { SystemDetail } from "../widgets/system/SystemDetail";

/** Detail-view registry. Unknown widget names render a 404 component (not a
 * blank screen or crash) — eng-review T7 guards this. */
const DETAILS: Record<string, () => JSX.Element> = {
  climate: ClimateDetail,
  stock: StockDetail,
  calendar: CalendarDetail,
  system: SystemDetail,
};

export function WidgetDetail() {
  const { name } = useParams<{ name: string }>();
  const Component = name ? DETAILS[name] : undefined;

  if (!Component) {
    return (
      <Card>
        <h1 className="font-display text-3xl uppercase tracking-tight text-primary mb-3" data-testid="widget-detail-404">
          Widget not found
        </h1>
        <p className="text-secondary">No widget called {name ? `"${name}"` : "—"}.</p>
        <Link to="/" className="hud-button-secondary mt-4 inline-block">Back to dashboard</Link>
      </Card>
    );
  }

  return <Component />;
}
