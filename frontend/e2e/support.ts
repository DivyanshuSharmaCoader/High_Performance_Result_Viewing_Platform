import { createHmac } from "node:crypto";

import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const BASE = process.env.E2E_BASE_DOMAIN ?? "localhost";
export const PORT = process.env.E2E_PORT ?? "8080";
export const MAILPIT = process.env.E2E_MAILPIT ?? "http://localhost:58025";

// Documented demo credentials created by `scorecode seed` (backend/app/seed.py) — development only.
export const DEMO_PASSWORD = "scorecode-demo-2026";
export const DEMO_TENANTS = {
  thapar: {
    slug: "thapar",
    owner: "registrar@thapar.example.com",
    name: "Thapar Institute of Engineering & Technology",
  },
  demoschool: { slug: "demoschool", owner: "principal@demoschool.example.com", name: "Demo Public School" },
  democoaching: {
    slug: "democoaching",
    owner: "director@democoaching.example.com",
    name: "Demo Coaching Academy",
  },
} as const;
export const DEMO_PLATFORM = {
  email: "ops@scorecode.example.com",
  totpSecret: "SCORECODEDEMOTOTPSECRETKEYAAAAAA",
};

export const url = (host: string, path = "/") => `http://${host ? `${host}.` : ""}${BASE}:${PORT}${path}`;

export function uniq(prefix: string): string {
  return `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits) — same algorithm the authenticator app uses. */
export function totp(secretB32: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secretB32.replace(/=+$/, "").toUpperCase())
    bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const hmac = createHmac("sha1", key).update(counter).digest();
  const offset = hmac[hmac.length - 1]! & 0xf;
  const code = (hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return code.toString().padStart(6, "0");
}

export async function signIn(
  page: Page,
  slug: string,
  loginId: string,
  password = DEMO_PASSWORD,
): Promise<void> {
  await page.goto(url(slug, "/login"));
  await page.getByLabel("Email or enrollment number").fill(loginId);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** Newest email to `to` from Mailpit, polling until it arrives (the worker sends asynchronously). */
export async function latestEmail(
  to: string,
  timeoutMs = 20_000,
): Promise<{ subject: string; text: string }> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}&limit=1`);
    const data = (await res.json()) as { messages?: { ID: string; Subject: string }[] };
    const first = data.messages?.[0];
    if (first) {
      const msg = (await (await fetch(`${MAILPIT}/api/v1/message/${first.ID}`)).json()) as {
        Subject: string;
        Text: string;
      };
      return { subject: msg.Subject, text: msg.Text };
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No email to ${to} within ${timeoutMs} ms`);
}

export function linkFrom(text: string, pattern: RegExp): string {
  const m = text.match(pattern);
  if (!m) throw new Error(`No link matching ${pattern} in email`);
  return m[0];
}

/**
 * Create a throwaway institution through the real self-serve sign-up API (sign-up → email → verify),
 * so destructive tests never touch shared demo tenants. Node can't resolve *.localhost, so requests go
 * to the proxy's IP with an explicit Host header.
 */
export async function createTenantViaSignup(
  request: APIRequestContext,
  name: string,
): Promise<{ slug: string; email: string }> {
  const host = { Host: `${BASE}:${PORT}` };
  const origin = `http://127.0.0.1:${PORT}`;
  await request.get(`${origin}/api/v1/auth/csrf`, { headers: host });
  const csrf = (await request.storageState()).cookies.find((c) => c.name.endsWith("sc_csrf"))?.value ?? "";
  const email = `${uniq("owner")}@e2e.example.com`;
  const slug = uniq("e2e-");
  const res = await request.post(`${origin}/api/v1/signup`, {
    headers: { ...host, "X-CSRF-Token": csrf },
    data: {
      email,
      full_name: "E2E Owner",
      institution_name: name,
      institution_type: "school",
      slug,
      password: "an-e2e-owner-passphrase",
    },
  });
  expect(res.status(), await res.text()).toBe(202);
  const mail = await latestEmail(email);
  const token = linkFrom(mail.text, /token=[\w-]+/).slice("token=".length);
  const verify = await request.post(`${origin}/api/v1/signup/verify`, {
    headers: { ...host, "X-CSRF-Token": csrf },
    data: { token },
  });
  expect(verify.status(), await verify.text()).toBe(200);
  return { slug, email };
}

/** Call the API from inside the page, exactly as the SPA does (same origin, cookies and CSRF header).
 *  Node itself can't resolve *.localhost, so requests are made by the browser. */
export async function apiAs<T = unknown>(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const result = await page.evaluate(
    async ({ method, path, body }) => {
      const csrf = document.cookie.match(/(?:^|; )(?:__Host-)?sc_csrf=([^;]+)/)?.[1] ?? "";
      const res = await fetch(path, {
        method,
        headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json", Accept: "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return { ok: res.ok, status: res.status, text: await res.text() };
    },
    { method, path, body },
  );
  if (!result.ok) throw new Error(`${method} ${path} → ${result.status}: ${result.text}`);
  return (result.text ? JSON.parse(result.text) : undefined) as T;
}
