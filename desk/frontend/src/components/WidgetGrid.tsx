import type { ReactNode } from "react";

/** Responsive widget grid. iPad landscape (~1366×1024): 3 cols, 5 tiles
 * laid out as 3+2 rows. Mobile portrait: 1 col stack. Mid-size: 2 cols.
 * Was lg:grid-cols-4 in v0.4 — bumped to 3 in v0.5 when the 5th tile
 * (Oura) was added; lg:grid-cols-4 would have orphaned the fifth tile. */
export function WidgetGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-[minmax(180px,_auto)]">
      {children}
    </div>
  );
}
