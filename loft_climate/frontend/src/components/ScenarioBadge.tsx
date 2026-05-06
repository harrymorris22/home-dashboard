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
        <span className="hud-label">Current scenario</span>
        <UrgencyDot urgency={urgency} label={urgency} />
      </div>
      <div className={`font-display text-3xl uppercase tracking-tight ${urgencyText[urgency]}`}>
        {scenario.replaceAll("_", " ")}
      </div>
      {prompts.length > 0 && (
        <ul className="text-sm space-y-1 text-primary">
          {prompts.map((p) => (
            <li key={p}>• {p}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
