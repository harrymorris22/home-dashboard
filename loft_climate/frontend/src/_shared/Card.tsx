import { type HTMLAttributes, type ReactNode } from "react";

/** Sports-HUD card primitive: flat surface, hairline border, sharp 4px corners.
 *
 * Shipped via `hud-card` / `hud-card-strong` utility classes defined in each
 * consuming app's globals.css. The visual contract is identical across apps —
 * change here once, applies everywhere.
 *
 * `strong` switches to a higher-emphasis border (2px primary, used for the
 * single most important card on a screen). Use sparingly.
 */
export function Card({
  children,
  className = "",
  strong = false,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode; strong?: boolean }) {
  const base = strong ? "hud-card-strong" : "hud-card";
  return (
    <div className={`${base} p-5 ${className}`} {...rest}>
      {children}
    </div>
  );
}
