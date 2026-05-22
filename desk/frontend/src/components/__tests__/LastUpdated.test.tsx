import { describe, expect, test, vi, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";

import { LastUpdated } from "../LastUpdated";

afterEach(() => {
  vi.useRealTimers();
});

describe("LastUpdated", () => {
  test("renders nothing when ts is null", () => {
    const { container } = render(<LastUpdated ts={null} />);
    expect(container.firstChild).toBeNull();
  });

  test("renders nothing when ts is undefined", () => {
    const { container } = render(<LastUpdated ts={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  test("renders relativeTime for an ISO string timestamp", () => {
    vi.useFakeTimers();
    const now = new Date("2026-05-22T12:00:00.000Z");
    vi.setSystemTime(now);
    const fiveSecondsAgo = new Date(now.getTime() - 5000).toISOString();
    render(<LastUpdated ts={fiveSecondsAgo} />);
    expect(screen.getByText(/ago|just now/)).toBeInTheDocument();
  });

  test("renders relativeTime for an epoch-ms number timestamp", () => {
    vi.useFakeTimers();
    const now = new Date("2026-05-22T12:00:00.000Z");
    vi.setSystemTime(now);
    const fiveSecondsAgoMs = now.getTime() - 5000;
    render(<LastUpdated ts={fiveSecondsAgoMs} />);
    expect(screen.getByText(/ago|just now/)).toBeInTheDocument();
  });

  test("re-renders every 5s so the displayed age stays honest", () => {
    vi.useFakeTimers();
    const now = new Date("2026-05-22T12:00:00.000Z");
    vi.setSystemTime(now);
    const sixSecondsAgo = new Date(now.getTime() - 6000).toISOString();
    render(<LastUpdated ts={sixSecondsAgo} />);
    expect(screen.getByLabelText("last updated").textContent).toMatch(/6s ago/);

    // advanceTimersByTime fires pending timers AND advances Date.now() in
    // sync. After +10s, the 5s setInterval has fired twice, triggering
    // re-renders via the internal setState. Original timestamp + 10s = 16s ago.
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByLabelText("last updated").textContent).toMatch(/16s ago/);
  });
});
