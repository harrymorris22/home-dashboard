import { describe, expect, test } from "vitest";

import { ageSecondsToText, relativeTime } from "../time";

describe("relativeTime", () => {
  const now = new Date("2026-05-01T12:00:00Z");
  test("just now", () => {
    expect(relativeTime("2026-05-01T11:59:58Z", now)).toBe("just now");
  });
  test("seconds ago", () => {
    expect(relativeTime("2026-05-01T11:59:30Z", now)).toBe("30s ago");
  });
  test("minutes ago", () => {
    expect(relativeTime("2026-05-01T11:30:00Z", now)).toBe("30 min ago");
  });
  test("hours ago", () => {
    expect(relativeTime("2026-05-01T08:00:00Z", now)).toBe("4h ago");
  });
  test("missing returns dash", () => {
    expect(relativeTime(null)).toBe("—");
  });
});

describe("ageSecondsToText", () => {
  test("seconds", () => {
    expect(ageSecondsToText(30)).toBe("30s old");
  });
  test("minutes", () => {
    expect(ageSecondsToText(180)).toBe("3 min old");
  });
  test("missing", () => {
    expect(ageSecondsToText(null)).toBe("—");
  });
});
