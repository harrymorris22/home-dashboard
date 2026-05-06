import type { CurrentState, Recommendations, ZoneId, BlindGroupId } from "../api/types";
import { Card } from "./glass/Card";
import { type Urgency, urgencyText, urgencyClass, maxUrgency } from "../lib/urgency";
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
  const reasons: string[] = [];
  for (const g of Object.values(rec.by_blind_group)) reasons.push(...g.reasons);
  for (const z of Object.values(rec.by_zone)) reasons.push(...z.reasons);
  const filtered = reasons.filter((r) => r && r.trim().length > 0);
  if (filtered.length === 0) return null;
  const unique = Array.from(new Set(filtered));
  unique.sort((a, b) => b.length - a.length);
  return unique[0];
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

  return (
    <Card strong className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="hud-label">What to do</span>
        <UrgencyDot urgency={urgency} label={urgency} />
      </div>

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

          return (
            <li key={zone} className="flex items-center gap-2">
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
