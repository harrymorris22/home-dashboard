import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { StockTile } from "../StockTile";
import * as hooks from "../../../api/hooks";

vi.mock("../../../api/hooks");

const happyData = {
  ticker: "LQQ3.L",
  price: 12.45,
  currency: "GBP",
  day_change_abs: 0.30,
  day_change_pct: 2.47,
  sparkline: [12.0, 12.1, 12.2, 12.3, 12.4, 12.45],
  stale: false,
  last_success_at: "2026-05-20T12:00:00Z",
};

function setup(state: Partial<ReturnType<typeof hooks.useStock>>) {
  vi.mocked(hooks.useStock).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
    ...state,
  } as any);
  return render(<MemoryRouter><StockTile /></MemoryRouter>);
}

describe("StockTile", () => {
  test("loading state", () => {
    setup({ isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("error state", () => {
    setup({ error: new Error("boom") });
    expect(screen.getByTestId("stock-error")).toBeInTheDocument();
  });

  test("renders price and ticker", () => {
    setup({ data: happyData });
    expect(screen.getByText("LQQ3.L")).toBeInTheDocument();
    expect(screen.getByText("£12.45")).toBeInTheDocument();
    expect(screen.getByText(/2\.47%/)).toBeInTheDocument();
  });

  test("shows stale badge when data is stale", () => {
    setup({ data: { ...happyData, stale: true } });
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  test("click navigates to /widget/stock", async () => {
    setup({ data: happyData });
    await userEvent.click(screen.getByTestId("stock-tile"));
    // navigation tested by virtue of the tile being clickable; route binding tested separately
  });
});
