import { Card } from "../_shared/Card";
import { type Urgency, urgencyText } from "../_shared/urgency";
import { formatHumidity, formatTemp } from "../_shared/format";
import { UrgencyDot } from "./UrgencyDot";

export type ZoneCardProps = {
  zone: string;
  label: string;
  temp_c: number | null | undefined;
  humidity_pct: number | null | undefined;
  urgency?: Urgency;
};

export function ZoneCard({
  label,
  temp_c,
  humidity_pct,
  urgency = "green",
}: ZoneCardProps) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="hud-label">{label}</h3>
        <UrgencyDot urgency={urgency} />
      </div>
      <div className={`hud-display ${urgencyText[urgency]}`}>
        {formatTemp(temp_c ?? null)}
      </div>
      <div className="flex justify-between text-sm text-secondary">
        <span>RH {formatHumidity(humidity_pct ?? null)}</span>
      </div>
    </Card>
  );
}
