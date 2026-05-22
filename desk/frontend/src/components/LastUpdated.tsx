import { useEffect, useState } from "react";

import { relativeTime } from "../_shared/time";

/** Small "updated Ns ago" badge that re-renders every 5s so the displayed
 * age stays honest between SWR refetches.
 *
 * Accepts both ISO 8601 strings (server-side timestamps from our API, e.g.
 * `last_success_at`, `last_ping_ts`) AND epoch-ms numbers (SWR's
 * `dataUpdatedAt` field for endpoints that don't expose a server-side
 * timestamp). The dual signature lets every tile use the same component
 * without per-callsite conversion.
 *
 * Per-instance setInterval — at 4 tiles total, the overhead is trivial
 * (~5 timer firings per second across the app). A shared TickProvider
 * Context would be premature abstraction at this scale.
 */
export function LastUpdated({ ts }: { ts: string | number | null | undefined }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);
  if (ts === null || ts === undefined) return null;
  const iso = typeof ts === "number" ? new Date(ts).toISOString() : ts;
  return (
    <span className="text-secondary text-xs" aria-label="last updated">
      {relativeTime(iso)}
    </span>
  );
}
