import { type Urgency, urgencyClass } from "../lib/urgency";

export function UrgencyDot({ urgency, label }: { urgency: Urgency; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full ${urgencyClass[urgency]}`}
        aria-label={`urgency ${urgency}`}
      />
      {label && <span className="text-xs uppercase tracking-wider opacity-70">{label}</span>}
    </span>
  );
}
