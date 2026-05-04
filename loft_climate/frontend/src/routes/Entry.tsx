import { ManualEntryForm } from "../components/ManualEntryForm";

export function Entry() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Manual entry</h1>
      <p className="text-sm opacity-70 max-w-2xl">
        Capture a snapshot of all four zones. Fields auto-fill from your last submission, so
        you only edit what changed. Add the optional feedback section to capture what you
        actually did and how it felt — that's the ground truth your thresholds get tuned against.
      </p>
      <ManualEntryForm />
    </div>
  );
}
