import { WidgetGrid } from "../components/WidgetGrid";
import { CalendarTile } from "../widgets/calendar/CalendarTile";
import { ClimateTile } from "../widgets/climate/ClimateTile";
import { StockTile } from "../widgets/stock/StockTile";
import { SystemTile } from "../widgets/system/SystemTile";

/** Grid of all widget tiles. v1 ships 4 tiles. */
export function Home() {
  return (
    <WidgetGrid>
      <ClimateTile />
      <StockTile />
      <CalendarTile />
      <SystemTile />
    </WidgetGrid>
  );
}
