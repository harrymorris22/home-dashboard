import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { SystemTile } from "../SystemTile";
import * as hooks from "../../../api/hooks";

vi.mock("../../../api/hooks");

function setup(state: Partial<ReturnType<typeof hooks.useSystem>>) {
  vi.mocked(hooks.useSystem).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
    ...state,
  } as any);
  return render(<MemoryRouter><SystemTile /></MemoryRouter>);
}

describe("SystemTile", () => {
  test("loading state", () => {
    setup({ isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("error state", () => {
    setup({ error: new Error("boom") });
    expect(screen.getByTestId("system-error")).toBeInTheDocument();
  });

  test("renders CPU temp, disk, internet uptime", () => {
    setup({
      data: {
        cpu_pct: 23,
        cpu_temp_c: 42.5,
        disk_pct: 67,
        mem_pct: 41,
        internet_24h_pct: 99.5,
        lan_24h_pct: 100,
        last_ping_ts: "2026-05-20T12:00:00Z",
      },
    });
    expect(screen.getByText("43°C")).toBeInTheDocument();
    expect(screen.getByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/100%/)).toBeInTheDocument();
    expect(screen.getByLabelText("last updated")).toBeInTheDocument();
  });

  test("thermal missing renders dash, not crash (critical-gap)", () => {
    setup({
      data: {
        cpu_pct: 23,
        cpu_temp_c: null,
        disk_pct: 67,
        mem_pct: 41,
        internet_24h_pct: 99.5,
        lan_24h_pct: 100,
        last_ping_ts: null,
      },
    });
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  test("internet ping pending shows dash", () => {
    setup({
      data: {
        cpu_pct: 23,
        cpu_temp_c: 42.5,
        disk_pct: 67,
        mem_pct: 41,
        internet_24h_pct: null,
        lan_24h_pct: null,
        last_ping_ts: null,
      },
    });
    // Internet row shows "—".
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
