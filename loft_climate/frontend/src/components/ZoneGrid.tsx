import { type Recommendations, type SensorReading, ZONE_IDS, type ZoneId } from "../api/types";
import { maxUrgency, type Urgency } from "../lib/urgency";
import { ZoneCard } from "./ZoneCard";

const LABEL: Record<ZoneId, string> = {
  mezzanine: "Office",
  downstairs: "Downstairs",
  ceiling_apex: "Ceiling apex",
  bedroom: "Bedroom",
};

export function ZoneGrid({
  sensors,
  recommendations,
}: {
  sensors: Record<string, SensorReading>;
  recommendations: Recommendations;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {ZONE_IDS.map((zone) => {
        const r = sensors[zone];
        const window_rec = recommendations.by_zone[zone];
        const blind_group = zone === "mezzanine" ? "mezz" : zone === "downstairs" ? "downstairs" : zone === "bedroom" ? "bedroom" : null;
        const blind_rec = blind_group ? recommendations.by_blind_group[blind_group] : undefined;
        const urgencies: Urgency[] = [window_rec?.urgency || "green"];
        if (blind_rec) urgencies.push(blind_rec.urgency);
        return (
          <ZoneCard
            key={zone}
            zone={zone}
            label={LABEL[zone]}
            temp_c={r?.temp_c}
            humidity_pct={r?.humidity_pct}
            urgency={maxUrgency(urgencies)}
          />
        );
      })}
    </div>
  );
}
