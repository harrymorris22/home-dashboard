import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { CalendarTile } from "../CalendarTile";
import * as hooks from "../../../api/hooks";
import { ApiError } from "../../../api/client";

vi.mock("../../../api/hooks");

function setup(state: Partial<ReturnType<typeof hooks.useCalendar>>) {
  vi.mocked(hooks.useCalendar).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
    ...state,
  } as any);
  return render(<MemoryRouter><CalendarTile /></MemoryRouter>);
}

describe("CalendarTile", () => {
  test("loading state", () => {
    setup({ isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("ical_url unconfigured shows setup instruction", () => {
    setup({ error: new ApiError(503, { error: "ical_url_not_configured", instruction: "Set ical_url" }) });
    expect(screen.getByTestId("calendar-unconfigured")).toBeInTheDocument();
  });

  test("upstream failure shows generic error", () => {
    setup({ error: new ApiError(502, { error: "ical_fetch_failed" }) });
    expect(screen.getByTestId("calendar-error")).toBeInTheDocument();
  });

  test("renders next event", () => {
    const inFuture = new Date(Date.now() + 30 * 60_000).toISOString();
    setup({
      data: {
        next: { title: "Standup", starts_at: inFuture, location: "Room A", all_day: false },
        today: [],
      },
    });
    expect(screen.getByText("Standup")).toBeInTheDocument();
    expect(screen.getByText(/in /)).toBeInTheDocument();
  });

  test("no upcoming events", () => {
    setup({ data: { next: null, today: [] } });
    expect(screen.getByText(/no upcoming events/i)).toBeInTheDocument();
  });
});
