import type { CurrentState, Recommendations, ZoneId } from "../api/types";
import { Card } from "../_shared/Card";
import { type Urgency, urgencyText } from "../_shared/urgency";
import { UrgencyDot } from "./UrgencyDot";

const ZONE_LABEL: Record<string, string> = {
  mezzanine: "office",
  downstairs: "downstairs",
  ceiling_apex: "apex",
  bedroom: "bedroom",
};

const GROUP_LABEL: Record<string, string> = {
  mezz: "office",
  downstairs: "downstairs",
  bedroom: "bedroom",
};

const ZONE_ORDER: ZoneId[] = ["mezzanine", "downstairs", "ceiling_apex", "bedroom"];
const ZONE_INDEX: Record<ZoneId, number> = {
  mezzanine: 0,
  downstairs: 1,
  ceiling_apex: 2,
  bedroom: 3,
};
const URGENCY_RANK: Record<Urgency, number> = { red: 0, amber: 1, green: 2 };

type Task = {
  id: string;
  actuator: "blind" | "window";
  zoneIdx: number;
  verb: string;
  hint: string;
  done: boolean;
  urgency: Urgency;
};

function blindVerb(group: string, target: number): string {
  const label = GROUP_LABEL[group] ?? group;
  // Binary blinds: engine emits 0 or 100. Treat >=75 as down, <=25 as up,
  // anything else as a partial position (rare with Tahoma binary blinds).
  if (target >= 75) return `Pull ${label} blinds down`;
  if (target <= 25) return `Raise ${label} blinds`;
  return `Set ${label} blinds to ${target}%`;
}

function windowVerb(zone: string, target: boolean): string {
  const label = ZONE_LABEL[zone] ?? zone;
  return target ? `Open ${label} window` : `Close ${label} window`;
}

function isBlindDone(target: number, current: number | undefined): boolean {
  if (current === undefined) return false;
  if (target >= 75 && current >= 75) return true;
  if (target <= 25 && current <= 25) return true;
  return target === current;
}

/** Pure task-list derivation. Test-friendly. */
function buildTasks(rec: Recommendations, currentState?: CurrentState): Task[] {
  const tasks: Task[] = [];

  // Blinds — 3 groups
  for (const g of Object.values(rec.by_blind_group)) {
    if (g.scenario === "neutral" || g.silence) continue;
    const current = currentState?.blinds?.[g.group];
    tasks.push({
      id: `blind:${g.group}`,
      actuator: "blind",
      zoneIdx:
        g.group === "mezz"
          ? ZONE_INDEX.mezzanine
          : g.group === "downstairs"
          ? ZONE_INDEX.downstairs
          : ZONE_INDEX.bedroom,
      verb: blindVerb(g.group, g.blind_pct),
      hint: g.reasons[0] ?? "",
      done: isBlindDone(g.blind_pct, current),
      urgency: g.urgency,
    });
  }

  // Windows — 4 zones
  for (const z of Object.values(rec.by_zone)) {
    if (z.window_open === null || z.silence) continue;
    const current = currentState?.windows?.[z.zone];
    const done = current !== undefined && current === z.window_open;
    tasks.push({
      id: `window:${z.zone}`,
      actuator: "window",
      zoneIdx: ZONE_INDEX[z.zone as ZoneId] ?? 99,
      verb: windowVerb(z.zone, z.window_open),
      hint: z.reasons[0] ?? "",
      done,
      urgency: z.urgency,
    });
  }

  return tasks;
}

/** Sort: undone first (urgency desc, then zone, then windows before blinds).
 * Done tasks after, same secondary sort. */
function sortTasks(tasks: Task[]): Task[] {
  const rank = (t: Task) => {
    const doneWeight = t.done ? 1000 : 0;
    const urgencyWeight = URGENCY_RANK[t.urgency] * 100;
    const zoneWeight = t.zoneIdx * 10;
    const actuatorWeight = t.actuator === "window" ? 0 : 1;
    return doneWeight + urgencyWeight + zoneWeight + actuatorWeight;
  };
  return [...tasks].sort((a, b) => rank(a) - rank(b));
}

/** Collect silence-only reasons for the fallback caption when there's no
 * fired reason anywhere. Matches v0.15 pickWhy's two-pass shape. */
function silenceFallback(rec: Recommendations): string | null {
  const firedCount =
    Object.values(rec.by_blind_group).filter((g) => !g.silence).length +
    Object.values(rec.by_zone).filter((z) => !z.silence).length;
  if (firedCount > 0) return null;
  const silenceReasons: string[] = [];
  for (const g of Object.values(rec.by_blind_group)) silenceReasons.push(...g.reasons);
  for (const z of Object.values(rec.by_zone)) silenceReasons.push(...z.reasons);
  const unique = Array.from(
    new Set(silenceReasons.filter((r) => r && r.trim().length > 0)),
  );
  if (unique.length === 0) return null;
  unique.sort((a, b) => b.length - a.length);
  return unique[0];
}

export function ActionPanel({
  rec,
  currentState,
}: {
  rec: Recommendations;
  currentState?: CurrentState;
}) {
  const urgency: Urgency = rec.global.urgency;
  const tasks = sortTasks(buildTasks(rec, currentState));
  const undoneCount = tasks.filter((t) => !t.done).length;
  const doneCount = tasks.length - undoneCount;
  const silenceLine = silenceFallback(rec);

  // HA cover state should populate `currentState.blinds` for every group the
  // engine fired on. When it's empty AND we DO have blind recommendations,
  // Tahoma is offline or the entity mapping is broken.
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
          ⚠ Blind state unknown — mark them below.
        </div>
      )}

      {tasks.length === 0 ? (
        <p
          className={`font-display text-2xl sm:text-3xl uppercase leading-snug ${urgencyText[urgency]}`}
        >
          Nothing to do — your loft is in the comfort band.
        </p>
      ) : (
        <ul className="space-y-3">
          {tasks.map((t, i) => {
            const prev = tasks[i - 1];
            const isFirstDone = t.done && (!prev || !prev.done);
            return (
              <li
                key={t.id}
                className={
                  isFirstDone
                    ? "grid grid-cols-[22px_1fr] gap-3 border-t border-secondary/30 pt-3"
                    : "grid grid-cols-[22px_1fr] gap-3"
                }
              >
                {t.done ? (
                  <span
                    aria-label="done"
                    className="mt-0.5 inline-flex h-5 w-5 items-center justify-center border-2 border-secondary bg-secondary text-surface text-xs font-bold"
                  >
                    ✓
                  </span>
                ) : (
                  <span
                    aria-label="pending"
                    className={`mt-0.5 inline-block h-5 w-5 border-2 ${
                      t.urgency === "red"
                        ? "border-tertiary"
                        : "border-primary"
                    } bg-surface`}
                  />
                )}
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span
                    className={
                      t.done
                        ? "text-secondary line-through text-sm"
                        : "text-primary font-bold text-base leading-tight"
                    }
                  >
                    {t.verb}
                  </span>
                  {t.hint && (
                    <span
                      className={`text-xs leading-snug ${
                        t.done ? "text-secondary/70" : "text-secondary"
                      }`}
                    >
                      {t.hint}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {tasks.length === 0 && silenceLine && (
        <p className="text-xs text-secondary">Why: {silenceLine}</p>
      )}

      {undoneCount > 0 && doneCount > 0 && (
        <p className="text-xs text-secondary text-right">
          {doneCount}/{tasks.length} done
        </p>
      )}

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

