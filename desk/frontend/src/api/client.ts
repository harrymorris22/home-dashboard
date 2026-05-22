/** Tiny typed fetch wrapper + SWR fetcher.
 *
 * Copied from loft_climate's pattern, kept lightweight. If both apps grow more
 * complex APIs (auth headers, request signing, etc.) this is a candidate to
 * move into @home/ui later.
 */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    // Read as text first so we can fall back if JSON parsing fails — a
    // Response body can only be consumed once, so we can't try .json()
    // then .text() on the same Response.
    const text = await res.text();
    let detail: unknown;
    try {
      const body = JSON.parse(text);
      // FastAPI HTTPException(detail=X) wraps the response body as
      // {"detail": X}. Unwrap so callers see the inner value uniformly.
      // Convention: every backend error response in this app flows through
      // FastAPI's HTTPException, so the unwrap is always safe.
      detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail: unknown }).detail
          : body;
    } catch {
      detail = text;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T,>(url: string) => request<T>(url),
  post: <T,>(url: string, body?: unknown) =>
    request<T>(url, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

export const fetcher = <T,>(url: string) => api.get<T>(url);
