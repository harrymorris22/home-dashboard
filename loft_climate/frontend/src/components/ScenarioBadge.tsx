import { Card } from "./glass/Card";
import { type Urgency, urgencyText } from "../lib/urgency";
import { UrgencyDot } from "./UrgencyDot";

export function ScenarioBadge({
  scenario,
  urgency,
  prompts,
}: {
  scenario: string;
  urgency: Urgency;
  prompts: string[];
}) {
  return (
    <Card strong className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider opacity-70">Current scenario</span>
        <UrgencyDot urgency={urgency} label={urgency} />
      </div>
      <div className={`text-2xl font-semibold ${urgencyText[urgency]}`}>
        {scenario.replaceAll("_", " ")}
      </div>
      {prompts.length > 0 && (
        <ul className="text-sm space-y-1 opacity-90">
          {prompts.map((p) => (
            <li key={p}>• {p}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
