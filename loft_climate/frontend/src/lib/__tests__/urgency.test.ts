import { describe, expect, test } from "vitest";

import { maxUrgency, urgencyClass, urgencyText } from "../../_shared/urgency";

describe("urgency", () => {
  test("maxUrgency picks highest", () => {
    expect(maxUrgency(["green", "amber", "red"])).toBe("red");
    expect(maxUrgency(["green", "green"])).toBe("green");
    expect(maxUrgency(["amber", "green"])).toBe("amber");
    expect(maxUrgency([])).toBe("green");
  });

  test("class maps cover all levels", () => {
    expect(urgencyClass.green).toBeTruthy();
    expect(urgencyClass.amber).toBeTruthy();
    expect(urgencyClass.red).toBeTruthy();
    expect(urgencyText.green).toBeTruthy();
  });
});
