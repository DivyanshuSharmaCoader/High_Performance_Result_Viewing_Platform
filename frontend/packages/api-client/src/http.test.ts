// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, request } from "./http";

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "sc_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("request", () => {
  it("sends the CSRF cookie value as a header on unsafe methods", async () => {
    document.cookie = "sc_csrf=abc123";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    await request("POST", "/api/v1/auth/login", { json: { a: 1 } });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("abc123");
    expect(init.credentials).toBe("same-origin");
  });

  it("turns problem+json into ApiError with field errors and retry hints", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "validation-failed",
          detail: "Some fields need attention.",
          errors: [{ field: "email", message: "Enter a valid email" }],
        }),
        { status: 422, headers: { "Content-Type": "application/problem+json" } },
      ),
    );
    const err = await request("GET", "/api/v1/me").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).fieldErrors()).toEqual({ email: "Enter a valid email" });
  });

  it("reports network failures as status 0", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await request("GET", "/api/v1/me").catch((e: unknown) => e)) as ApiError;
    expect(err.isNetwork).toBe(true);
  });

  it("captures Retry-After for rate-limited responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ code: "rate-limited" }), {
        status: 429,
        headers: { "Retry-After": "7" },
      }),
    );
    const err = (await request("GET", "/api/v1/me").catch((e: unknown) => e)) as ApiError;
    expect(err.retryAfter).toBe(7);
  });
});
