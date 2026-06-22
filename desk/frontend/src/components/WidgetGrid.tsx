import type { ReactNode } from "react";

/** Responsive widget grid. iPad landscape (~1366×1024): 4 cols, 2 rows.
 * Mobile portrait: 1 col stack. Mid-size: 2 cols. */
export function WidgetGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 auto-rows-[minmax(180px,_auto)]">
      {children}
    </div>
  );
}
