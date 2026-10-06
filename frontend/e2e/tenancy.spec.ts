import { expect, test } from "@playwright/test";

import {
  BASE,
  DEMO_PASSWORD,
  DEMO_PLATFORM,
  DEMO_TENANTS,
  PORT,
  createTenantViaSignup,
  signIn,
  totp,
  url,
} from "./support";

test("two tenants render with their own branding from one build (P4.5)", async ({ page }) => {
  const brand = async (slug: string) => {
    await page.goto(url(slug, "/login"));
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    return page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--sc-brand").trim(),
    );
  };
  const thapar = await brand("thapar");
  const coaching = await brand("democoaching");
  expect(thapar).toBe("#8c1d18");
  expect(coaching).toBe("#6d28d9");
  await expect(page).toHaveTitle(/Demo Coaching Academy/);
});

test("a session on one institution's host is useless on another's (isolation demo)", async ({ page }) => {
  await signIn(page, "thapar", DEMO_TENANTS.thapar.owner);
  await page.goto(url("demoschool", "/admin"));
  await expect(page).toHaveURL(/demoschool\.[^/]+\/login/);
  // Even sending Thapar's session cookie explicitly to Demo School's API is rejected.
  const cookies = await page.context().cookies(url("thapar"));
  const session = cookies.find((c) => c.name.endsWith("sc_session"));
  expect(session).toBeTruthy();
  // Node can't resolve *.localhost, so address the proxy directly and set the Host header (as a browser would).
  const res = await page.request.get(`http://127.0.0.1:${PORT}/api/v1/me`, {
    headers: { Host: `demoschool.${BASE}:${PORT}`, Cookie: `sc_session=${session!.value}` },
  });
  expect(res.status()).toBe(401);
});

test("unknown institution address explains itself", async ({ page }) => {
  await page.goto(url("no-such-school-xyz", "/"));
  await expect(page.getByText("There's no institution here")).toBeVisible();
});

test("platform admin suspends a tenant and its portal shows the unavailable page (P4.7)", async ({
  page,
  browser,
  request,
}) => {
  const institution = `E2E Suspend ${Date.now()}`;
  const { slug } = await createTenantViaSignup(request, institution);
  await page.goto(url("admin", "/login"));
  await page.getByLabel("Work email").fill(DEMO_PLATFORM.email);
  await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByLabel("Authenticator code").fill(totp(DEMO_PLATFORM.totpSecret));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  await page.getByRole("link", { name: "Institutions" }).click();
  await page.getByRole("searchbox", { name: "Search institutions" }).fill(slug);
  await page.getByRole("link", { name: institution }).click();
  await page.getByRole("button", { name: "Suspend" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Reason/).fill("E2E suspension test");
  await dialog.getByRole("textbox").last().fill(slug);
  await dialog.getByRole("button", { name: "Suspend institution" }).click();
  await expect(page.getByText("Institution suspended")).toBeVisible();

  // Other API processes converge within the 5 s in-process cache bound (app/modules/tenancy/service.py).
  const visitor = await (await browser.newContext()).newPage();
  await expect(async () => {
    await visitor.goto(url(slug, "/login"));
    await expect(visitor.getByText("Portal temporarily unavailable")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 15_000 });

  await page.getByRole("button", { name: "Reactivate" }).click();
  await page
    .getByRole("dialog")
    .getByLabel(/Reason/)
    .fill("E2E restore");
  await page.getByRole("dialog").getByRole("button", { name: "Reactivate" }).click();
  await expect(page.getByText("Institution reactivated")).toBeVisible();
  await expect(async () => {
    await visitor.reload();
    await expect(visitor.getByRole("heading", { name: "Sign in" })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 15_000 });
});
