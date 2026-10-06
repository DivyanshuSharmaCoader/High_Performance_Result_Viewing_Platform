import { expect, test } from "@playwright/test";

import { DEMO_TENANTS, signIn, uniq, url } from "./support";

const COACHING = DEMO_TENANTS.democoaching;

test("P7.3: create a scheme from a template, preview a change and save it as version 2", async ({ page }) => {
  const name = `Unit tests ${uniq("")}`;
  await signIn(page, COACHING.slug, COACHING.owner);
  await page.goto(url(COACHING.slug, "/admin/grading"));
  await expect(page.getByRole("heading", { name: "Grading", exact: true })).toBeVisible();
  // the seeded default scheme
  await expect(page.getByRole("link", { name: "Test series (marks and ranks)" })).toBeVisible();

  await page.getByRole("button", { name: "New scheme" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Simple letter grades (A–F)").click();
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByRole("button", { name: "Create scheme" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();

  // Default samples 86, 64, 38 (out of 100): 188/300 = 62.67%; every paper clears the template's 35%.
  const preview = page.locator("section", { has: page.getByRole("heading", { name: "Try it" }) });
  await expect(preview.getByText("62.67%")).toBeVisible();
  await expect(preview.getByText("Pass", { exact: true })).toBeVisible();

  const passMark = page.getByLabel("Pass mark per paper (%) (optional)");
  await passMark.fill("40");
  await expect(preview.getByText("Fail", { exact: true })).toBeVisible(); // 38 < 40 now fails

  await page.getByLabel("What changed? (optional)").fill("Pass mark raised to 40%");
  await page.getByRole("button", { name: "Save as version 2" }).click();
  await expect(page.locator("[data-sonner-toast]").getByText("Saved as version 2")).toBeVisible();
  await expect(page.getByText("Pass mark raised to 40%")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Pass mark per paper (%) (optional)")).toHaveValue("40");
});
