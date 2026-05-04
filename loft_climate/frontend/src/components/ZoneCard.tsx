import { Card } from "./glass/Card";
import { type Urgency, urgencyText } from "../lib/urgency";
import { formatHumidity, formatTemp } from "../lib/format";
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
        <h3 className="text-sm uppercase tracking-wider opacity-70">{label}</h3>
        <UrgencyDot urgency={urgency} />
      </div>
      <div className={`text-4xl font-semibold ${urgencyText[urgency]}`}>
        {formatTemp(temp_c ?? null)}
      </div>
      <div className="flex justify-between text-sm opacity-70">
        <span>RH {formatHumidity(humidity_pct ?? null)}</span>
      </div>
    </Card>
  );
}
