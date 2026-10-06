/**
 * Thin fetch wrapper used by every app.
 *
 * - Same-origin requests only (the tenant is the host — never a parameter).
 * - Double-submit CSRF: unsafe methods send X-CSRF-Token = the non-HttpOnly csrf cookie; if the cookie is
 *   missing it is fetched once from /api/v1/auth/csrf.
 * - Errors are RFC 9457 problem+json, surfaced as ApiError with field-level details.
 */

export interface FieldError {
  field: string | null;
  message: string;
  type?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string;
  readonly field: string | undefined;
  readonly errors: FieldError[];
  readonly retryAfter: number | undefined;
  readonly requestId: string | undefined;
  readonly body: Record<string, unknown>;

  constructor(status: number, body: Record<string, unknown>) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong.";
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.code = typeof body.code === "string" ? body.code : `http-${status}`;
    this.title = typeof body.title === "string" ? body.title : "Request failed";
    this.detail = detail;
    this.field = typeof body.field === "string" ? body.field : undefined;
    this.errors = Array.isArray(body.errors) ? (body.errors as FieldError[]) : [];
    this.retryAfter = typeof body.retry_after === "number" ? body.retry_after : undefined;
    this.requestId = typeof body.request_id === "string" ? body.request_id : undefined;
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }

  /** Map server validation errors onto form fields. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (this.field) out[this.field] = this.detail;
    for (const e of this.errors) if (e.field && !out[e.field]) out[e.field] = e.message;
    return out;
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  for (const part of document.cookie.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return null;
}

export function csrfToken(): string | null {
  return readCookie("__Host-sc_csrf") ?? readCookie("sc_csrf");
}

let csrfPromise: Promise<void> | null = null;

async function ensureCsrf(): Promise<string> {
  const existing = csrfToken();
  if (existing) return existing;
  csrfPromise ??= fetch("/api/v1/auth/csrf", { credentials: "same-origin" }).then(() => undefined);
  await csrfPromise;
  csrfPromise = null;
  return csrfToken() ?? "";
}

export interface RequestOptions {
  json?: unknown;
  body?: BodyInit;
  query?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  idempotencyKey?: string;
}

export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(options.query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  let body = options.body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  if (UNSAFE.has(method)) headers["X-CSRF-Token"] = await ensureCsrf();
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  let response: Response;
  try {
    response = await fetch(url.pathname + url.search, {
      method,
      headers,
      body: body ?? null,
      credentials: "same-origin",
      signal: options.signal ?? null,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, {
      code: "network-error",
      title: "Can't reach ScoreCode",
      detail: "Check your internet connection and try again.",
    });
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text.slice(0, 200) };
    }
  }
  if (!response.ok) {
    const problem = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
    const retry = response.headers.get("Retry-After");
    if (retry && problem.retry_after === undefined) problem.retry_after = Number(retry);
    throw new ApiError(response.status, problem);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, options),
  post: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>("POST", path, { ...options, json }),
  put: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>("PUT", path, { ...options, json }),
  patch: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>("PATCH", path, { ...options, json }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>("DELETE", path, options),
  upload: <T>(path: string, form: FormData, options?: RequestOptions) =>
    request<T>("POST", path, { ...options, body: form }),
};

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
