import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { OuraTile } from "../OuraTile";
import * as hooks from "../../../api/hooks";
import { ApiError } from "../../../api/client";
import type { OuraData } from "../../../api/hooks";

vi.mock("../../../api/hooks");

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

describe("OuraTile", () => {
  test("loading state", () => {
    setup({ isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("generic error state", () => {
    setup({ error: new Error("boom") });
    expect(screen.getByTestId("oura-error")).toBeInTheDocument();
  });

  test("unconfigured-token error renders instruction", () => {
    setup({
      error: new ApiError(503, {
        error: "oura_pat_token_not_configured",
        instruction: "Get a PAT at cloud.ouraring.com → ...",
      }),
    });
    expect(screen.getByTestId("oura-unconfigured")).toBeInTheDocument();
    expect(screen.getByText(/cloud\.ouraring\.com/)).toBeInTheDocument();
  });

  test("token-invalid error renders distinct instruction", () => {
    setup({
      error: new ApiError(503, {
        error: "oura_token_invalid",
        instruction: "PAT rejected by Oura. Re-create one.",
      }),
    });
    expect(screen.getByTestId("oura-token-invalid")).toBeInTheDocument();
    expect(screen.getByText(/Re-create one/)).toBeInTheDocument();
  });

  test("happy path renders today with thousands separator + yesterday", () => {
    setup({ data: BASE });
    expect(screen.getByTestId("oura-tile")).toBeInTheDocument();
    expect(screen.getByText("8,432")).toBeInTheDocument();
    expect(screen.getByText(/yesterday 11,204/)).toBeInTheDocument();
    expect(screen.getByLabelText("last updated")).toBeInTheDocument();
  });

  test("step_count: 0 renders as literal '0', NOT '—'", () => {
    // The most likely-to-ship-broken edge case. Falsy-check (`||`) would
    // turn 0 into '—'; nullish-check (`??`) preserves the early-morning state.
    setup({
      data: { ...BASE, step_count: 0, step_count_yesterday: 11204 },
    });
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  test("today null, yesterday present → headline '—' + syncing subtitle", () => {
    setup({
      data: { ...BASE, step_count: null, step_count_yesterday: 11204 },
    });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/yesterday 11,204 · syncing today/)).toBeInTheDocument();
  });

  test("both null → headline '—' + 'No step data yet'", () => {
    setup({
      data: { ...BASE, step_count: null, step_count_yesterday: null },
    });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/No step data yet/)).toBeInTheDocument();
  });

  test("large number uses en-GB thousands separator", () => {
    setup({ data: { ...BASE, step_count: 12345 } });
    expect(screen.getByText("12,345")).toBeInTheDocument();
  });

  test("stale badge appears when data is stale", () => {
    setup({ data: { ...BASE, stale: true } });
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  test("yesterday null but today present → 'yesterday —' subtitle", () => {
    setup({ data: { ...BASE, step_count: 8432, step_count_yesterday: null } });
    expect(screen.getByText("8,432")).toBeInTheDocument();
    expect(screen.getByText(/yesterday —/)).toBeInTheDocument();
  });
});
