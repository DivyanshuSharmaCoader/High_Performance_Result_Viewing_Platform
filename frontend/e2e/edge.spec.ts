import { expect, test, type Page } from "@playwright/test";

import { url } from "./support";

/**
 * The edge (infra/caddy/Caddyfile) in front of the real API, as the DAST baseline found it (P15.4):
 * isolation headers on every kind of response, HTML that is always revalidated, a 404 for an asset a
 * deploy removed, and pages whose own headers (the verify page's) are kept, not overwritten.
 */

function cspViolations(page: Page): string[] {
  const seen: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy/i.test(m.text())) seen.push(m.text());
  });
  return seen;
}

test("app routes, assets and API answers carry the edge's headers", async ({ request }) => {
  const app = await request.get(url("thapar", "/login"));
  expect(app.status()).toBe(200);
  const h = app.headers();
  expect(h["cache-control"]).toBe("no-cache"); // index.html under an app route: a deploy is picked up
  expect(h["cross-origin-opener-policy"]).toBe("same-origin");
  expect(h["cross-origin-resource-policy"]).toBe("same-origin");
  expect(h["cross-origin-embedder-policy"]).toBe("credentialless");
  expect(h["content-security-policy"]).toContain("script-src 'self';");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["server"]).toBeUndefined();

  const asset = (await app.text()).match(/\/assets\/[^"]+\.js/)?.[0];
  expect(asset).toBeTruthy();
  const hashed = await request.get(url("thapar", asset!));
  expect(hashed.headers()["cache-control"]).toBe("public, max-age=31536000, immutable");

  const gone = await request.get(url("thapar", "/assets/index-removed-by-a-deploy.js"));
  expect(gone.status()).toBe(404);
  expect(gone.headers()["cache-control"]).toBe("no-store");

  const api = await request.get(url("thapar", "/api/v1/tenant/config"));
  expect(api.status()).toBe(200);
  expect(api.headers()["cross-origin-opener-policy"]).toBe("same-origin");
  expect(api.headers()["server"]).toBeUndefined();
});

test("the verify page keeps its own policy, and its hash-pinned stylesheet applies", async ({ page }) => {
  const violations = cspViolations(page);
  const response = await page.goto(url("verify", "/v?code=ZZZZZZZZZZZZZZZZZZZZZZZZZZ"));
  expect(response?.status()).toBe(404); // unknown code: the friendly page
  const h = response!.headers();
  expect(h["referrer-policy"]).toBe("no-referrer"); // the code is in the address: never passed on
  expect(h["cross-origin-embedder-policy"]).toBe("require-corp");
  expect(h["content-security-policy"]).not.toContain("unsafe-inline");
  await expect(page.getByRole("heading", { name: "No statement found" })).toBeVisible();
  // Blocked styles would leave the browser default (8px); the page's stylesheet sets 0.
  expect(await page.evaluate(() => getComputedStyle(document.body).margin)).toBe("0px");
  expect(violations).toEqual([]);
});

test("a tenant page runs under its policy without violations", async ({ page }) => {
  const violations = cspViolations(page);
  await page.goto(url("thapar", "/login"));
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  expect(await page.evaluate(() => window.crossOriginIsolated)).toBe(true); // COOP + COEP took effect
  expect(violations).toEqual([]);
});
