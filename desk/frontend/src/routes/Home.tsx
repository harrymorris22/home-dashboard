import { WidgetGrid } from "../components/WidgetGrid";
import { CalendarTile } from "../widgets/calendar/CalendarTile";
import { ClimateTile } from "../widgets/climate/ClimateTile";
import { OuraTile } from "../widgets/oura/OuraTile";
import { StockTile } from "../widgets/stock/StockTile";
import { SystemTile } from "../widgets/system/SystemTile";

/** Grid of all widget tiles. v0.5 ships 5 tiles in a 3+2 layout. */
export function Home() {
  return (
    <WidgetGrid>
      <ClimateTile />
      <StockTile />
      <CalendarTile />
      <SystemTile />
      <OuraTile />
    </WidgetGrid>
  );
}
