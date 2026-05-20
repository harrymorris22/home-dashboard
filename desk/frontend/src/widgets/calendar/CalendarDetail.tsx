import { Card } from "../../_shared/Card";
import { formatTime, untilText } from "../../_shared/time";
import { useCalendar } from "../../api/hooks";

export function CalendarDetail() {
  const { data, error, isLoading } = useCalendar();

  if (isLoading) {
    return <Card><p className="text-secondary">Loading…</p></Card>;
  }

  if (error || !data) {
    return <Card><p className="text-secondary">Calendar unavailable.</p></Card>;
  }

  return (
    <Card className="flex flex-col gap-4">
      <h1 className="font-display text-3xl uppercase tracking-tight text-primary">Today</h1>
      {data.today.length === 0 ? (
        <p className="text-secondary">No events today.</p>
      ) : (
        <ul className="space-y-3">
          {data.today.map((ev) => (
            <li key={`${ev.starts_at}-${ev.title}`} className="border-t border-secondary/30 pt-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-bold text-primary text-lg">{ev.title}</span>
                <span className="hud-label whitespace-nowrap">
                  {ev.all_day ? "all day" : formatTime(ev.starts_at)}
                </span>
              </div>
              {!ev.all_day && (
                <p className="text-xs text-secondary">{untilText(ev.starts_at)}</p>
              )}
              {ev.location && <p className="text-xs text-secondary">{ev.location}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
