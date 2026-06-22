import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { ClimateTile } from "../ClimateTile";
import * as hooks from "../../../api/hooks";
import type { ClimateData } from "../../../api/hooks";

vi.mock("../../../api/hooks");

const BASE: ClimateData = {
  scenario: "neutral",
  urgency: "green",
  office_temp_c: 22,
  window_actions: [],
  blind_actions: [],
  prompt: null,
  ts: "2026-05-20T12:00:00Z",
  stale: false,
  last_success_at: "2026-05-20T12:00:00Z",
};

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

  test("renders data state with scenario, urgency, and office temp", () => {
    setup({
      data: {
        ...BASE,
        scenario: "hot_sunny_breeze",
        urgency: "amber",
        office_temp_c: 24.5,
        prompt: "Open windows",
      },
    });
    expect(screen.getByText(/hot sunny breeze/i)).toBeInTheDocument();
    expect(screen.getByText(/24\.5/)).toBeInTheDocument();
    expect(screen.getByText(/Office/)).toBeInTheDocument();
    expect(screen.getByLabelText("last updated")).toBeInTheDocument();
  });

  test("shows stale badge when data is stale", () => {
    setup({ data: { ...BASE, stale: true, last_success_at: "2026-05-20T11:00:00Z" } });
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  test("click opens loft.harrymorris.me in new window", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    setup({ data: BASE });
    await userEvent.click(screen.getByTestId("climate-tile"));
    expect(openSpy).toHaveBeenCalledWith("https://loft.harrymorris.me/", "_blank", "noopener");
    openSpy.mockRestore();
  });

  // ── v0.4.0: action lines ────────────────────────────────────────────────

  test("no action lines when both arrays empty", () => {
    setup({ data: BASE });
    expect(screen.queryByTestId("climate-window-actions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("climate-blind-actions")).not.toBeInTheDocument();
  });

  test("renders window 'open' action with friendly label", () => {
    setup({
      data: { ...BASE, window_actions: [{ zone: "mezzanine", action: "open" }] },
    });
    expect(screen.getByTestId("climate-window-actions")).toHaveTextContent("Open office");
  });

  test("renders window 'close' action with friendly label", () => {
    setup({
      data: { ...BASE, window_actions: [{ zone: "bedroom", action: "close" }] },
    });
    expect(screen.getByTestId("climate-window-actions")).toHaveTextContent("Close bedroom");
  });

  test("joins multiple window actions with ' · '", () => {
    setup({
      data: {
        ...BASE,
        window_actions: [
          { zone: "mezzanine", action: "open" },
          { zone: "bedroom", action: "close" },
        ],
      },
    });
    expect(screen.getByTestId("climate-window-actions")).toHaveTextContent(
      "Open office · Close bedroom",
    );
  });

  test("renders blind 'lower' action with target percentage", () => {
    setup({
      data: {
        ...BASE,
        blind_actions: [
          { group: "mezz", current_pct: 100, target_pct: 30, direction: "lower" },
        ],
      },
    });
    expect(screen.getByTestId("climate-blind-actions")).toHaveTextContent(
      "Lower office blinds to 30%",
    );
  });

  test("renders blind 'raise' action with target percentage", () => {
    setup({
      data: {
        ...BASE,
        blind_actions: [
          { group: "bedroom", current_pct: 0, target_pct: 100, direction: "raise" },
        ],
      },
    });
    expect(screen.getByTestId("climate-blind-actions")).toHaveTextContent(
      "Raise bedroom blinds to 100%",
    );
  });

  test("window_actions undefined renders no window line (rolling-deploy safety)", () => {
    const { window_actions: _omit, ...partial } = BASE;
    setup({ data: partial as ClimateData });
    expect(screen.queryByTestId("climate-window-actions")).not.toBeInTheDocument();
  });

  test("blind_actions undefined renders no blind line (rolling-deploy safety)", () => {
    const { blind_actions: _omit, ...partial } = BASE;
    setup({ data: partial as ClimateData });
    expect(screen.queryByTestId("climate-blind-actions")).not.toBeInTheDocument();
  });

  test("action lines use text-primary (distinguished from text-secondary prompt)", () => {
    setup({
      data: {
        ...BASE,
        window_actions: [{ zone: "mezzanine", action: "open" }],
        prompt: "supplementary context",
      },
    });
    expect(screen.getByTestId("climate-window-actions").className).toMatch(/text-primary/);
    expect(screen.getByText("supplementary context").className).toMatch(/text-secondary/);
  });
});
