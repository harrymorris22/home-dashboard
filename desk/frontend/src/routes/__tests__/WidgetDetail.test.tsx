import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { WidgetDetail } from "../WidgetDetail";

// Stub all four detail components so we test only the registry/routing.
vi.mock("../../widgets/climate/ClimateDetail", () => ({ ClimateDetail: () => <div>climate-detail</div> }));
vi.mock("../../widgets/stock/StockDetail", () => ({ StockDetail: () => <div>stock-detail</div> }));
vi.mock("../../widgets/calendar/CalendarDetail", () => ({ CalendarDetail: () => <div>calendar-detail</div> }));
vi.mock("../../widgets/system/SystemDetail", () => ({ SystemDetail: () => <div>system-detail</div> }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/widget/:name" element={<WidgetDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WidgetDetail registry", () => {
  test("renders ClimateDetail for /widget/climate", () => {
    renderAt("/widget/climate");
    expect(screen.getByText("climate-detail")).toBeInTheDocument();
  });

  test("renders StockDetail for /widget/stock", () => {
    renderAt("/widget/stock");
    expect(screen.getByText("stock-detail")).toBeInTheDocument();
  });

  test("renders CalendarDetail for /widget/calendar", () => {
    renderAt("/widget/calendar");
    expect(screen.getByText("calendar-detail")).toBeInTheDocument();
  });

  test("renders SystemDetail for /widget/system", () => {
    renderAt("/widget/system");
    expect(screen.getByText("system-detail")).toBeInTheDocument();
  });

  test("unknown widget name renders 404 component, not crash (eng-review T7)", () => {
    renderAt("/widget/nonsense");
    expect(screen.getByTestId("widget-detail-404")).toBeInTheDocument();
  });
});
