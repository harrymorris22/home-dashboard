import type { CurrentState, Recommendations, ZoneId, BlindGroupId } from "../api/types";
import { Card } from "../_shared/Card";
import { type Urgency, urgencyText, urgencyClass, maxUrgency } from "../_shared/urgency";
import { UrgencyDot } from "./UrgencyDot";

const ZONE_LABEL: Record<string, string> = {
  mezzanine: "Office",
  downstairs: "Downstairs",
  ceiling_apex: "Ceiling apex",
  bedroom: "Bedroom",
};

const GROUP_LABEL: Record<string, string> = {
  mezz: "mezzanine",
  downstairs: "downstairs",
  bedroom: "bedroom",
};

const ZONE_TO_GROUP: Partial<Record<ZoneId, BlindGroupId>> = {
  mezzanine: "mezz",
  downstairs: "downstairs",
  bedroom: "bedroom",
};

const ZONE_ORDER: ZoneId[] = ["mezzanine", "downstairs", "ceiling_apex", "bedroom"];

function listJoin(items: string[]): string {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function blindWord(pct: number): string {
  if (pct >= 75) return "down";
  if (pct <= 25) return "up";
  return `${pct}%`;
}

function blindSummary(rec: Recommendations): string {
  const groups = Object.values(rec.by_blind_group);
  const fired = groups.filter((g) => g.scenario !== "neutral");
  if (fired.length === 0) return "no change";

  // Group by position word.
  const byPosition: Record<string, string[]> = {};
  for (const g of fired) {
    const word = blindWord(g.blind_pct);
    (byPosition[word] ||= []).push(GROUP_LABEL[g.group]);
  }
  const positions = Object.keys(byPosition);

  // Single uniform position across every actuator the engine cares about.
  if (positions.length === 1 && fired.length === groups.length) {
    return `all ${positions[0]} (${fired[0].blind_pct}%)`;
  }
  // Mixed — list each subset.
  const parts = positions.map((p) => `${listJoin(byPosition[p])} ${p}`);
  return parts.join("; ");
}

function windowSummary(rec: Recommendations): string {
  const zones = Object.values(rec.by_zone);
  const fired = zones.filter((z) => z.window_open !== null);
  if (fired.length === 0) return "no change";

  const open = fired.filter((z) => z.window_open === true).map((z) => ZONE_LABEL[z.zone]);
  const closed = fired.filter((z) => z.window_open === false).map((z) => ZONE_LABEL[z.zone]);

  if (open.length === zones.length) return "all open";
  if (closed.length === zones.length) return "all closed";

  const parts: string[] = [];
  if (open.length) parts.push(`${listJoin(open)} open`);
  if (closed.length) parts.push(`${listJoin(closed)} closed`);
  return parts.join("; ");
}

function pickWhy(rec: Recommendations): string | null {
  // v0.15: two-pass.
  //   Pass 1 — filter out silence-tagged reasons; a real fired-rule reason
  //            should always win the headline slot.
  //   Pass 2 — if no fired reason exists (weather offline, all-neutral),
  //            fall back to silence reasons so per-zone ↳ lines can
  //            deduplicate against a headline instead of showing the same
  //            string on every row.
  const firedReasons: string[] = [];
  const silenceReasons: string[] = [];
  for (const g of Object.values(rec.by_blind_group)) {
    (g.silence ? silenceReasons : firedReasons).push(...g.reasons);
  }
  for (const z of Object.values(rec.by_zone)) {
    (z.silence ? silenceReasons : firedReasons).push(...z.reasons);
  }
  const pick = (pool: string[]) => {
    const filtered = pool.filter((r) => r && r.trim().length > 0);
    if (filtered.length === 0) return null;
    const unique = Array.from(new Set(filtered));
    unique.sort((a, b) => b.length - a.length);
    return unique[0];
  };
  return pick(firedReasons) ?? pick(silenceReasons);
}

/** Combine per-zone blind + window reasoning into one line for the ↳
 * annotation. Returns null when both reasons are empty OR when both
 * duplicate the top-level headline (no new info to show). */
function zoneReasonLine(
  blindReason: string | undefined,
  windowReason: string | undefined,
  headline: string | null,
): string | null {
  const blindNew = blindReason && blindReason !== headline ? blindReason : null;
  const windowNew =
    windowReason && windowReason !== headline ? windowReason : null;
  if (!blindNew && !windowNew) return null;
  const parts: string[] = [];
  if (blindNew) parts.push(`Blinds: ${blindNew}`);
  if (windowNew) parts.push(`Window: ${windowNew}`);
  return parts.join(" · ");
}

function blindCurrent(pct: number): string {
  if (pct >= 75) return "down";
  if (pct <= 25) return "up";
  return `${pct}%`;
}

export function ActionPanel({
  rec,
  currentState,
}: {
  rec: Recommendations;
  currentState?: CurrentState;
}) {
  const blinds = blindSummary(rec);
  const windows = windowSummary(rec);
  const why = pickWhy(rec);
  const urgency: Urgency = rec.global.urgency;

  const allNeutral = blinds === "no change" && windows === "no change";

  // HA cover state should populate `currentState.blinds` for every group the
  // engine fired on. When it's empty AND we DO have blind recommendations,
  // Tahoma is offline or the entity mapping is broken. Surface it directly
  // so the user doesn't read the recommendation as a status statement.
  const hasBlindRecs = Object.keys(rec.by_blind_group).length > 0;
  const knownBlinds = Object.keys(currentState?.blinds ?? {}).length;
  const blindStateMissing = hasBlindRecs && knownBlinds === 0;

  return (
    <Card strong className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="hud-label">What to do</span>
        <UrgencyDot urgency={urgency} label={urgency} />
      </div>

      {blindStateMissing && (
        <div className="border border-primary rounded p-2 text-xs uppercase tracking-label font-bold text-primary">
          ⚠ Blind state unknown — Tahoma not reporting. Recommendations below
          are not based on current position.
        </div>
      )}

      {allNeutral ? (
        <p className={`font-display text-2xl sm:text-3xl uppercase leading-snug ${urgencyText[urgency]}`}>
          Nothing to do — your loft is in the comfort band.
        </p>
      ) : (
        <div className={`font-display text-2xl sm:text-3xl uppercase leading-snug ${urgencyText[urgency]}`}>
          <p>
            <span className="hud-label">Blinds:</span>{" "}
            {blinds}
          </p>
          <p>
            <span className="hud-label">Windows:</span>{" "}
            {windows}
          </p>
        </div>
      )}

      {why && <p className="text-sm text-secondary">Why: {why}</p>}

      <ul className="text-sm space-y-1.5 border-t border-secondary/30 pt-3">
        {ZONE_ORDER.map((zone) => {
          const window = rec.by_zone[zone];
          const groupId = ZONE_TO_GROUP[zone];
          const blind = groupId ? rec.by_blind_group[groupId] : undefined;
          const currentBlind = groupId ? currentState?.blinds?.[groupId] : undefined;
          const currentWindow = currentState?.windows?.[zone];

          // Build per-actuator phrases.
          // Recommendation-with-action ("blinds down (currently up)") is bold-ish prose;
          // no-recommendation falls back to a dim "engine has no opinion" annotation
          // so it doesn't get visually confused with a real instruction.
          const parts: { text: string; muted: boolean }[] = [];

          if (blind && blind.scenario !== "neutral") {
            const want = blind.blind_pct;
            let phrase = `blinds ${blindWord(want)} (${want}%)`;
            if (currentBlind !== undefined) {
              if (
                (want >= 75 && currentBlind >= 75) ||
                (want <= 25 && currentBlind <= 25) ||
                want === currentBlind
              ) {
                phrase += " ✓ already";
              } else {
                phrase += ` (currently ${blindCurrent(currentBlind)})`;
              }
            } else {
              // No HA cover state — annotate so the recommendation is not
              // misread as "your blinds are currently at this position".
              phrase += " (current unknown)";
            }
            parts.push({ text: phrase, muted: false });
          } else if (groupId) {
            const cur =
              currentBlind !== undefined ? ` (you have them ${blindCurrent(currentBlind)})` : "";
            parts.push({ text: `blinds — no recommendation${cur}`, muted: true });
          }

          if (window.window_open !== null) {
            const want = window.window_open;
            let phrase = `window ${want ? "open" : "closed"}`;
            if (currentWindow !== undefined) {
              if (currentWindow === want) phrase += " ✓ already";
              else phrase += ` (currently ${currentWindow ? "open" : "closed"})`;
            }
            parts.push({ text: phrase, muted: false });
          } else {
            const cur =
              currentWindow !== undefined
                ? ` (it's ${currentWindow ? "open" : "closed"})`
                : "";
            parts.push({ text: `window — no recommendation${cur}`, muted: true });
          }

          const urgencies: Urgency[] = [];
          if (blind) urgencies.push(blind.urgency);
          urgencies.push(window.urgency);
          const u = maxUrgency(urgencies);

          // v0.15: per-zone reasoning line. Combine blind + window reasons,
          // skip when both match the headline (no new info). ceiling_apex
          // has no blind group, so blindReason falls through as undefined.
          const blindReason = blind ? blind.reasons[0] : undefined;
          const windowReason = window.reasons[0];
          const reasonLine = zoneReasonLine(blindReason, windowReason, why);

          return (
            <li key={zone} className="flex flex-col gap-0.5">
              <div className="flex items-center gap-2">
                <span className={`inline-block h-2 w-2 rounded-full ${urgencyClass[u]}`} />
                <span className="text-secondary w-28">{ZONE_LABEL[zone]}:</span>
                <span className="text-primary">
                  {parts.map((p, i) => (
                    <span key={i} className={p.muted ? "text-secondary" : ""}>
                      {i > 0 && <span className="text-secondary"> · </span>}
                      {p.text}
                    </span>
                  ))}
                </span>
              </div>
              {reasonLine && (
                <div className="text-xs text-secondary pl-4">
                  ↳ {reasonLine}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {rec.prompts.length > 0 && (
        <ul className="text-xs space-y-1 text-secondary border-t border-secondary/30 pt-3">
          {rec.prompts.map((p) => (
            <li key={p}>• {p}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
