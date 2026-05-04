import { Card } from "./glass/Card";
import { type Recommendations, ZONE_IDS, BLIND_GROUP_IDS, type ZoneId } from "../api/types";
import { urgencyText } from "../lib/urgency";
import { formatBlind } from "../lib/format";
import { UrgencyDot } from "./UrgencyDot";

const ZONE_LABEL: Record<ZoneId, string> = {
  mezzanine: "Mezzanine",
  downstairs: "Downstairs",
  ceiling_apex: "Ceiling apex",
  bedroom: "Bedroom",
};

const GROUP_LABEL: Record<string, string> = {
  mezz: "Mezz blind",
  downstairs: "Downstairs blind",
  bedroom: "Bedroom blind",
};

export function RecommendationsPanel({ rec }: { rec: Recommendations }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Blinds</h2>
        <ul className="space-y-3">
          {BLIND_GROUP_IDS.map((g) => {
            const r = rec.by_blind_group[g];
            return (
              <li key={g} className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{GROUP_LABEL[g]}</span>
                  <span className={`font-semibold ${urgencyText[r.urgency]}`}>
                    {formatBlind(r.blind_pct)}
                  </span>
                </div>
                {r.reasons.length > 0 && (
                  <p className="text-xs opacity-70">{r.reasons[0]}</p>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3">Windows</h2>
        <ul className="space-y-3">
          {ZONE_IDS.map((z) => {
            const r = rec.by_zone[z];
            const state =
              r.window_open === null ? "no change" : r.window_open ? "Open" : "Closed";
            return (
              <li key={z} className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{ZONE_LABEL[z]}</span>
                  <span className={`font-semibold ${urgencyText[r.urgency]}`}>{state}</span>
                </div>
                {r.reasons.length > 0 && (
                  <p className="text-xs opacity-70">{r.reasons[0]}</p>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      {rec.rule_errors.length > 0 && (
        <Card className="lg:col-span-2 border-rose-500/40">
          <h2 className="text-sm uppercase tracking-wider text-rose-300 mb-2">
            Rule errors (degraded)
          </h2>
          <ul className="text-xs space-y-1 opacity-80">
            {rec.rule_errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="lg:col-span-2">
        <h2 className="text-sm uppercase tracking-wider opacity-70 mb-3 flex items-center gap-3">
          Global state
          <UrgencyDot urgency={rec.global.urgency} label={rec.global.urgency} />
        </h2>
        <p className="text-xs opacity-70">Scenario: {rec.global.scenario}</p>
      </Card>
    </div>
  );
}
