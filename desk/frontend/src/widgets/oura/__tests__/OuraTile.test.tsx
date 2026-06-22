import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { OuraTile } from "../OuraTile";
import * as hooks from "../../../api/hooks";
import * as swr from "swr";
import { ApiError } from "../../../api/client";
import type { OuraData } from "../../../api/hooks";

vi.mock("../../../api/hooks");
vi.mock("swr", async () => {
  const actual = await vi.importActual<typeof import("swr")>("swr");
  return {
    ...actual,
    mutate: vi.fn(),
  };
});

const BASE: OuraData = {
  step_count: 8432,
  step_count_yesterday: 11204,
  ts: "2026-06-22T12:00:00Z",
  stale: false,
  last_success_at: "2026-06-22T12:00:00Z",
};

function setup(state: Partial<ReturnType<typeof hooks.useOura>>) {
  vi.mocked(hooks.useOura).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
    ...state,
  } as any);
  return render(
    <MemoryRouter>
      <OuraTile />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(swr.mutate).mockClear();
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  window.history.replaceState({}, "", "/");
});

describe("OuraTile", () => {
  test("loading state", () => {
    setup({ isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("generic error state", () => {
    setup({ error: new Error("boom") });
    expect(screen.getByTestId("oura-error")).toBeInTheDocument();
  });

  test("oura_oauth_not_configured renders setup instruction", () => {
    setup({
      error: new ApiError(503, {
        error: "oura_oauth_not_configured",
        instruction: "Set Oura credentials in Add-on options.",
      }),
    });
    expect(screen.getByTestId("oura-unconfigured")).toBeInTheDocument();
    expect(screen.getByText(/Add-on options/)).toBeInTheDocument();
  });

  test("oura_not_connected renders 'Connect Oura →' headline", () => {
    setup({
      error: new ApiError(503, {
        error: "oura_not_connected",
        instruction: "Click Connect Oura.",
      }),
    });
    expect(screen.getByTestId("oura-not-connected")).toBeInTheDocument();
    expect(screen.getByText(/Connect Oura →/)).toBeInTheDocument();
  });

  test("oura_not_connected click navigates same-tab to /api/widgets/oura/oauth/start", async () => {
    const origLocation = window.location;
    // jsdom doesn't allow direct location.href assignment to navigate; spy on the setter.
    delete (window as any).location;
    (window as any).location = { ...origLocation, href: "/" };
    setup({
      error: new ApiError(503, { error: "oura_not_connected" }),
    });
    await userEvent.click(screen.getByTestId("oura-not-connected"));
    expect((window as any).location.href).toBe("/api/widgets/oura/oauth/start");
    (window as any).location = origLocation;
  });

  test("oura_token_invalid renders 'Reconnect Oura →' headline + explanatory subtitle", () => {
    setup({
      error: new ApiError(503, { error: "oura_token_invalid" }),
    });
    expect(screen.getByTestId("oura-token-invalid")).toBeInTheDocument();
    expect(screen.getByText(/Reconnect Oura →/)).toBeInTheDocument();
    expect(screen.getByText(/Token expired or revoked/)).toBeInTheDocument();
  });

  test("happy path renders thousands separator + yesterday + LastUpdated", () => {
    setup({ data: BASE });
    expect(screen.getByTestId("oura-tile")).toBeInTheDocument();
    expect(screen.getByText("8,432")).toBeInTheDocument();
    expect(screen.getByText(/yesterday 11,204/)).toBeInTheDocument();
    expect(screen.getByLabelText("last updated")).toBeInTheDocument();
  });

  test("step_count: 0 renders literal '0' (not '—')", () => {
    // The most likely-to-ship-broken edge case: `||` falsy-check would turn 0
    // into '—'; nullish-check (`??`) preserves the early-morning state.
    setup({ data: { ...BASE, step_count: 0 } });
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  test("today null + yesterday present → '—' headline + 'syncing today' subtitle", () => {
    setup({
      data: { ...BASE, step_count: null, step_count_yesterday: 11204 },
    });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/yesterday 11,204 · syncing today/)).toBeInTheDocument();
  });

  test("both null → '—' headline + 'No step data yet'", () => {
    setup({ data: { ...BASE, step_count: null, step_count_yesterday: null } });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/No step data yet/)).toBeInTheDocument();
  });

  test("large number uses en-GB thousands separator", () => {
    setup({ data: { ...BASE, step_count: 12345 } });
    expect(screen.getByText("12,345")).toBeInTheDocument();
  });

  test("stale badge appears when stale: true", () => {
    setup({ data: { ...BASE, stale: true } });
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  test("?connected=1 query param triggers SWR mutate", () => {
    window.history.replaceState({}, "", "/?connected=1");
    setup({ data: BASE });
    expect(swr.mutate).toHaveBeenCalledWith("/api/widgets/oura/summary");
  });

  test("?oauth_error query param also triggers SWR mutate", () => {
    window.history.replaceState({}, "", "/?oauth_error=token_exchange_failed");
    setup({ data: BASE });
    expect(swr.mutate).toHaveBeenCalledWith("/api/widgets/oura/summary");
  });

  test("query param is stripped from URL after consumption", () => {
    window.history.replaceState({}, "", "/?connected=1&keep=this");
    setup({ data: BASE });
    expect(window.location.search).toBe("?keep=this");
  });

  test("no query param → no mutate call", () => {
    setup({ data: BASE });
    expect(swr.mutate).not.toHaveBeenCalled();
  });
});
