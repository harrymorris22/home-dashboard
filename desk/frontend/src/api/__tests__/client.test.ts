import { describe, expect, test, vi, afterEach } from "vitest";

import { api, ApiError } from "../client";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  const responseInit = { status, headers: { "Content-Type": contentType } };
  const json = typeof body === "string" ? body : JSON.stringify(body);
  global.fetch = vi.fn().mockResolvedValue(
    new Response(json, responseInit),
  ) as unknown as typeof fetch;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("client.ts FastAPI detail unwrap", () => {
  test("FastAPI happy unwrap: {detail: {error: 'x'}} → apiErr.detail is {error: 'x'}", async () => {
    mockFetch(503, { detail: { error: "ical_url_not_configured", instruction: "Set it" } });
    try {
      await api.get("/api/test");
      expect.fail("expected ApiError");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const apiErr = e as ApiError;
      expect(apiErr.status).toBe(503);
      expect(apiErr.detail).toEqual({
        error: "ical_url_not_configured",
        instruction: "Set it",
      });
      // NOT the wrapped shape:
      expect((apiErr.detail as { detail?: unknown }).detail).toBeUndefined();
    }
  });

  test("non-FastAPI body without 'detail' key passes through unchanged", async () => {
    mockFetch(500, { error: "raw", trace: "stack" });
    try {
      await api.get("/api/test");
      expect.fail("expected ApiError");
    } catch (e) {
      const apiErr = e as ApiError;
      expect(apiErr.detail).toEqual({ error: "raw", trace: "stack" });
    }
  });

  test("{detail: null} unwraps to null", async () => {
    mockFetch(500, { detail: null });
    try {
      await api.get("/api/test");
      expect.fail("expected ApiError");
    } catch (e) {
      expect((e as ApiError).detail).toBeNull();
    }
  });

  test("non-JSON body falls back to text", async () => {
    // Build a Response with plain text and a Content-Type that res.json() will reject.
    const res = new Response("Internal Server Error", {
      status: 500,
      headers: { "Content-Type": "text/plain" },
    });
    global.fetch = vi.fn().mockResolvedValue(res) as unknown as typeof fetch;
    try {
      await api.get("/api/test");
      expect.fail("expected ApiError");
    } catch (e) {
      const apiErr = e as ApiError;
      expect(apiErr.status).toBe(500);
      expect(apiErr.detail).toBe("Internal Server Error");
    }
  });
});
