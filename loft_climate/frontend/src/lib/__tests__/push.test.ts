import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { disablePush, enablePush, getPushState, urlBase64ToUint8Array } from "../push";

describe("urlBase64ToUint8Array", () => {
  test("decodes URL-safe + with no padding", () => {
    // Encodes the string "hi"
    const arr = urlBase64ToUint8Array("aGk");
    expect(Array.from(arr)).toEqual([104, 105]);
  });
  test("decodes URL-safe with - and _", () => {
    // base64 of bytes [251, 240]: "+/A=" → URL-safe "-_A"
    const arr = urlBase64ToUint8Array("-_A");
    expect(Array.from(arr)).toEqual([251, 240]);
  });
  test("handles padded input", () => {
    const arr = urlBase64ToUint8Array("aGk=");
    expect(Array.from(arr)).toEqual([104, 105]);
  });
});

describe("getPushState", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockReturnValue({ matches: true }),
    });
  });
  test("reports installed when display-mode standalone", async () => {
    Object.defineProperty(global, "Notification", {
      writable: true,
      value: { permission: "default" },
    });
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { getRegistration: vi.fn().mockResolvedValue(undefined) },
    });
    const state = await getPushState();
    expect(state.installed).toBe(true);
    expect(state.permission).toBe("default");
    expect(state.swRegistered).toBe(false);
  });
});

describe("enablePush", () => {
  let originalFetch: typeof fetch;
  let originalNotification: any;
  beforeEach(() => {
    originalFetch = global.fetch;
    originalNotification = (global as any).Notification;
  });
  afterEach(() => {
    global.fetch = originalFetch;
    (global as any).Notification = originalNotification;
    vi.restoreAllMocks();
  });

  test("rejects when permission denied", async () => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        getRegistration: vi.fn().mockResolvedValue({}),
        register: vi.fn(),
      },
    });
    Object.defineProperty(global, "Notification", {
      writable: true,
      value: {
        permission: "denied",
        requestPermission: vi.fn().mockResolvedValue("denied"),
      },
    });
    await expect(enablePush()).rejects.toThrow(/Permission denied/);
  });

  test("subscribes successfully on permission grant", async () => {
    const sub = {
      endpoint: "https://web.push.apple.com/abc",
      toJSON: () => ({
        endpoint: "https://web.push.apple.com/abc",
        keys: { p256dh: "P", auth: "A" },
      }),
    };
    const reg = { pushManager: { subscribe: vi.fn().mockResolvedValue(sub) } };
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        getRegistration: vi.fn().mockResolvedValue(reg),
        register: vi.fn(),
        ready: Promise.resolve(reg),
      },
    });
    Object.defineProperty(global, "Notification", {
      writable: true,
      value: {
        permission: "default",
        requestPermission: vi.fn().mockResolvedValue("granted"),
      },
    });
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/push/vapid_public") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ public_key: "aGk" }),
        });
      }
      if (url === "/api/push/subscribe") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 1 }),
        });
      }
      return Promise.reject(new Error("unexpected URL " + url));
    }) as any;
    const result = await enablePush();
    expect(result).toEqual({ id: 1 });
  });
});

describe("disablePush", () => {
  test("noop when no SW registration", async () => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { getRegistration: vi.fn().mockResolvedValue(undefined) },
    });
    await expect(disablePush()).resolves.toBeUndefined();
  });
});
