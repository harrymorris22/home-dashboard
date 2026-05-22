import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { ClimateTile } from "../ClimateTile";
import * as hooks from "../../../api/hooks";

vi.mock("../../../api/hooks");

function setup(state: Partial<ReturnType<typeof hooks.useClimate>>) {
  vi.mocked(hooks.useClimate).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
    ...state,
  } as any);
  return render(
    <MemoryRouter>
      <ClimateTile />
    </MemoryRouter>,
  );
}

describe("ClimateTile", () => {
  test("renders loading state when isLoading", () => {
    setup({ isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders error state when hook returns error", () => {
    setup({ error: new Error("boom") });
    expect(screen.getByTestId("climate-error")).toBeInTheDocument();
  });

  test("renders data state with scenario and urgency", () => {
    setup({
      data: {
        scenario: "hot_sunny_breeze",
        urgency: "amber",
        bedroom_temp_c: 24.5,
        prompt: "Open windows",
        ts: "2026-05-20T12:00:00Z",
        stale: false,
        last_success_at: "2026-05-20T12:00:00Z",
      },
    });
    expect(screen.getByText(/hot sunny breeze/i)).toBeInTheDocument();
    expect(screen.getByText(/24\.5/)).toBeInTheDocument();
    // LastUpdated badge renders when data is present.
    expect(screen.getByLabelText("last updated")).toBeInTheDocument();
  });

  test("shows stale badge when data is stale", () => {
    setup({
      data: {
        scenario: "neutral",
        urgency: "green",
        bedroom_temp_c: 22,
        prompt: null,
        ts: "2026-05-20T12:00:00Z",
        stale: true,
        last_success_at: "2026-05-20T11:00:00Z",
      },
    });
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  test("click opens loft.harrymorris.me in new window", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    setup({
      data: {
        scenario: "neutral",
        urgency: "green",
        bedroom_temp_c: 22,
        prompt: null,
        ts: "2026-05-20T12:00:00Z",
        stale: false,
        last_success_at: "2026-05-20T12:00:00Z",
      },
    });
    await userEvent.click(screen.getByTestId("climate-tile"));
    expect(openSpy).toHaveBeenCalledWith("https://loft.harrymorris.me/", "_blank", "noopener");
    openSpy.mockRestore();
  });
});
