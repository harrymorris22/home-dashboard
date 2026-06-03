import { useNavigate } from "react-router-dom";

import { Card } from "../../_shared/Card";
import { untilText } from "../../_shared/time";
import { useCalendar } from "../../api/hooks";
import { ApiError } from "../../api/client";
import { LastUpdated } from "../../components/LastUpdated";

/** Calendar tile. Shows next event + countdown ("in N min").
 * Special-cases the "ical_url not configured" error (503) with a clear
 * setup instruction. */
export function CalendarTile() {
  const navigate = useNavigate();
  const { data, error, isLoading, dataUpdatedAt } = useCalendar();

  const onClick = () => navigate("/widget/calendar");

  if (isLoading) {
    return (
      <Card>
        <h2 className="hud-label">Calendar</h2>
        <p className="text-secondary text-sm mt-3">Loading…</p>
      </Card>
    );
  }

  if (error) {
    const apiErr = error as ApiError;
    const detail = (apiErr.detail as { error?: string; instruction?: string }) || {};
    const errorCode = detail.error;

    // Error code → user-facing message + test-id. Each known sub-error
    // gets actionable copy; unknown errors fall through to the generic
    // "unreachable" so we never crash on a new backend error code.
    let message = "Calendar source unreachable";
    let testId = "calendar-error";
    if (apiErr.status === 503 && errorCode === "ical_url_not_configured") {
      message = detail.instruction || "Set ical_url in Add-on options";
      testId = "calendar-unconfigured";
    } else if (errorCode === "ical_returned_html") {
      message =
        detail.instruction ||
        "Wrong URL type. Use the iCal Secret address ending in basic.ics.";
      testId = "calendar-html-response";
    }
    return (
      <Card>
        <h2 className="hud-label">Calendar</h2>
        <p className="text-secondary text-sm mt-3" data-testid={testId}>
          {message}
        </p>
      </Card>
    );
  }

  if (!data?.next) {
    return (
      <Card>
        <h2 className="hud-label">Calendar</h2>
        <p className="text-secondary text-sm mt-3">No upcoming events</p>
      </Card>
    );
  }

  const ev = data.next;
  return (
    <Card
      onClick={onClick}
      className="cursor-pointer hover:border-primary transition flex flex-col gap-2"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      data-testid="calendar-tile"
    >
      <div className="flex items-center justify-between">
        <h2 className="hud-label">Calendar</h2>
        <LastUpdated ts={dataUpdatedAt} />
      </div>
      <div className="font-display text-2xl uppercase tracking-tight text-primary line-clamp-2">
        {ev.title}
      </div>
      <p className="text-sm text-secondary">
        {ev.all_day ? "All day" : <span className="text-primary font-bold">{untilText(ev.starts_at)}</span>}
      </p>
      {ev.location && <p className="text-xs text-secondary line-clamp-1">{ev.location}</p>}
    </Card>
  );
}
