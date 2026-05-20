import { describe, expect, test } from "vitest";

import { formatBlind, formatHumidity, formatLux, formatTemp, roundBlind } from "../../_shared/format";

describe("formatTemp", () => {
  test("renders one decimal", () => {
    expect(formatTemp(24)).toBe("24.0°C");
    expect(formatTemp(23.456)).toBe("23.5°C");
  });
  test("handles missing", () => {
    expect(formatTemp(null)).toBe("—");
    expect(formatTemp(undefined)).toBe("—");
    expect(formatTemp(Number.NaN)).toBe("—");
  });
});

describe("formatHumidity", () => {
  test("rounds and adds %", () => {
    expect(formatHumidity(48.6)).toBe("49%");
  });
  test("handles missing", () => {
    expect(formatHumidity(null)).toBe("—");
  });
});

describe("formatLux", () => {
  test("uses k for >= 1000", () => {
    expect(formatLux(12000)).toBe("12.0k lx");
    expect(formatLux(800)).toBe("800 lx");
  });
});

describe("roundBlind / formatBlind", () => {
  test("rounds to nearest 25", () => {
    expect(roundBlind(0)).toBe(0);
    expect(roundBlind(13)).toBe(25);
    expect(roundBlind(38)).toBe(50);
    expect(roundBlind(73)).toBe(75);
    expect(roundBlind(100)).toBe(100);
  });
  test("formatBlind labels extremes", () => {
    expect(formatBlind(0)).toBe("Up (0%)");
    expect(formatBlind(100)).toBe("Down (100%)");
    expect(formatBlind(50)).toBe("50%");
  });
});
