import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { DEMO_TENANTS, latestEmail, linkFrom, signIn, uniq, url } from "./support";

const thapar = DEMO_TENANTS.thapar;

test.describe("staff sign-in for each role (P3.11)", () => {
  test("owner signs in, sees the admin dashboard and signs out", async ({ page }) => {
    await signIn(page, thapar.slug, thapar.owner);
    await expect(page).toHaveURL(url(thapar.slug, "/admin"));
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Office of the Registrar");
    await expect(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Staff" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(url(thapar.slug, "/login"));
    await page.goto(url(thapar.slug, "/admin"));
    await expect(page).toHaveURL(/\/login\?next=%2Fadmin/);
  });

  test("wrong password shows a generic error and keeps the user on the page", async ({ page }) => {
    await page.goto(url(thapar.slug, "/login"));
    await page.getByLabel("Email or enrollment number").fill(thapar.owner);
    await page.getByLabel("Password", { exact: true }).fill("definitely-wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("We couldn't sign you in")).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  });

  for (const role of ["Faculty", "Administrator"] as const) {
    test(`an invited ${role.toLowerCase()} accepts by email and gets the right access`, async ({
      page,
      browser,
    }) => {
      const email = `${uniq(role.toLowerCase())}@thapar.example.com`;
      await signIn(page, thapar.slug, thapar.owner);
      await page.goto(url(thapar.slug, "/admin/staff"));
      await page.getByRole("button", { name: "Invite staff" }).first().click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Full name").fill(`E2E ${role}`);
      await dialog.getByLabel("Work email").fill(email);
      await dialog.getByText(role, { exact: true }).click();
      await dialog.getByRole("button", { name: "Send invitation" }).click();
      await expect(page.locator("[data-sonner-toast]").getByText("Invitation sent")).toBeVisible();

      const mail = await latestEmail(email);
      const link = linkFrom(mail.text, /http:\/\/\S+\/accept-invite\?token=[\w-]+/);
      expect(link).toContain(`${thapar.slug}.`);
      const context = await browser.newContext();
      const invitee = await context.newPage();
      await invitee.goto(link);
      await expect(invitee.getByLabel("Name")).toHaveValue(`E2E ${role}`);
      await invitee.getByLabel("Password", { exact: true }).fill("an-e2e-staff-passphrase");
      await invitee.getByLabel("Confirm password").fill("an-e2e-staff-passphrase");
      await invitee.getByRole("button", { name: "Create account" }).click();
      if (role === "Administrator") {
        await expect(invitee).toHaveURL(url(thapar.slug, "/admin"));
        await expect(
          invitee.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Staff" }),
        ).toBeVisible();
      } else {
        await expect(invitee).toHaveURL(url(thapar.slug, "/marking")); // faculty start at their marking
        const nav = invitee.getByRole("navigation", { name: "Main" });
        await expect(nav.getByRole("link", { name: "Marks entry" })).toBeVisible();
        await expect(nav.getByRole("link", { name: "Staff" })).toHaveCount(0);
        await invitee.goto(url(thapar.slug, "/admin/staff"));
        await expect(invitee.getByText("You don't have access to this page")).toBeVisible();
      }
      await context.close();
    });
  }

  test("sign-in and dashboard have no detectable accessibility violations", async ({ page }) => {
    await page.goto(url(thapar.slug, "/login"));
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    const login = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(login.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
    await signIn(page, thapar.slug, thapar.owner);
    await expect(page.getByText("Plan usage")).toBeVisible();
    const dashboard = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(dashboard.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
});
