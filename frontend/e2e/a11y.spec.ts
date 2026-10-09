import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_PLATFORM, DEMO_TENANTS, settled, signIn, totp, url } from "./support";

/**
 * NFR-13 (WCAG 2.1 AA): automated axe checks across the screens people use most. Axe finds about a third
 * of WCAG problems; the rest need the manual review the NFR also asks for.
 */
const THAPAR = DEMO_TENANTS.thapar;

async function expectAccessible(page: Page, what: string): Promise<void> {
  await settled(page);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const found = result.violations.map(
    (v) => `${what}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(" ")}`,
  );
  expect(found).toEqual([]);
}

test("public pages: the site, an unknown address, the verify page", async ({ page }) => {
  await page.goto(url("", "/"));
  await expect(page.locator("main")).toBeVisible();
  await expectAccessible(page, "site home");
  await page.goto(url("no-such-institution-a11y", "/"));
  await expect(page.getByText("There's no institution here")).toBeVisible();
  await expectAccessible(page, "unknown institution");
  await page.goto(url("verify", "/v"));
  await expect(page.getByRole("heading", { name: "Verify a statement of marks" })).toBeVisible();
  await expectAccessible(page, "verify form");
});

test("the student portal on a phone", async ({ browser }) => {
  const page = await (await browser.newContext({ viewport: { width: 360, height: 780 } })).newPage();
  await signIn(page, THAPAR.slug, "102401001", DEMO_PASSWORD);
  await expect(page).toHaveURL(url(THAPAR.slug, "/me"));
  await expectAccessible(page, "student home");
  await page.goto(url(THAPAR.slug, "/me/account"));
  await expect(page.getByRole("heading").first()).toBeVisible();
  await expectAccessible(page, "student account");
});

test("the exam office's main screens", async ({ page }) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  for (const [path, what] of [
    ["/admin/exams", "exams"],
    ["/admin/students", "students"],
    ["/admin/imports", "imports"],
    ["/admin/grading", "grading"],
    ["/admin/plan", "plan"],
    ["/admin/audit-log", "audit log"],
    ["/admin/settings", "settings"],
    ["/admin/staff", "staff"],
  ] as const) {
    await page.goto(url(THAPAR.slug, path));
    await expect(page.getByRole("heading").first()).toBeVisible();
    await expectAccessible(page, what);
  }
});

test("the platform console", async ({ page }) => {
  await page.goto(url("admin", "/login"));
  await expectAccessible(page, "console sign-in");
  await page.getByLabel("Work email").fill(DEMO_PLATFORM.email);
  await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByLabel("Authenticator code").fill(totp(DEMO_PLATFORM.totpSecret));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expectAccessible(page, "console overview");
  await page.getByRole("link", { name: "Institutions" }).click();
  await expect(page.getByRole("searchbox", { name: "Search institutions" })).toBeVisible();
  await expectAccessible(page, "console institutions");
});
