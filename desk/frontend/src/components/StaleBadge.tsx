/** Small badge for widget tiles when data is stale (served from cache after
 * upstream failure). Appears in the corner of affected tiles. */
export function StaleBadge() {
  return <span className="stale-badge" aria-label="data is stale">stale</span>;
}
