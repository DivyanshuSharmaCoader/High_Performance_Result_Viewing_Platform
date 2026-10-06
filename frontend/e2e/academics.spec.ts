import { expect, test } from "@playwright/test";

import { DEMO_TENANTS, signIn, uniq, url } from "./support";

test("academic structure: create, edit, archive and restore a course (P5.3)", async ({ page }) => {
  const code = uniq("E2E").toUpperCase().slice(0, 14);
  await signIn(page, "thapar", DEMO_TENANTS.thapar.owner);
  await page.goto(url("thapar", "/admin/academics/courses"));
  await expect(page.getByRole("link", { name: /Courses/ })).toHaveAttribute("aria-current", "page");

  await page.getByRole("button", { name: "New course" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Code").fill(code);
  await dialog.getByLabel("Name").fill("Compiler Design");
  await dialog.getByLabel("Credits (optional)").fill("3.5");
  await dialog.getByRole("button", { name: "Create course" }).click();
  await expect(page.locator("[data-sonner-toast]").getByText(`Course ${code} created`)).toBeVisible();

  await page.getByRole("searchbox", { name: "Search courses" }).fill(code);
  const row = page.getByRole("row", { name: new RegExp(code) });
  await expect(row).toContainText("Compiler Design");
  await expect(row).toContainText("3.5");

  await row.getByRole("button", { name: `Actions for ${code}` }).click();
  await page.getByRole("menuitem", { name: "Edit course" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill("Compiler Construction");
  await page.getByRole("dialog").getByRole("button", { name: "Save changes" }).click();
  await expect(row).toContainText("Compiler Construction");

  await row.getByRole("button", { name: `Actions for ${code}` }).click();
  await page.getByRole("menuitem", { name: "Archive" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Archive" }).click();
  await expect(page.getByText("No courses match")).toBeVisible();

  await page.getByText("Show archived").click();
  await expect(row).toContainText("Archived");
  await row.getByRole("button", { name: `Actions for ${code}` }).click();
  await page.getByRole("menuitem", { name: "Restore" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Restore" }).click();
  await expect(row).not.toContainText("Archived");
});

test("academic structure: duplicate codes are reported on the field", async ({ page }) => {
  await signIn(page, "thapar", DEMO_TENANTS.thapar.owner);
  await page.goto(url("thapar", "/admin/academics/courses"));
  await page.getByRole("button", { name: "New course" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Code").fill("ucs301");
  await dialog.getByLabel("Name").fill("Duplicate");
  await dialog.getByRole("button", { name: "Create course" }).click();
  await expect(dialog.getByText("A course with this code already exists.")).toBeVisible();
});

test("academic structure: sessions show seeded terms and the current session", async ({ page }) => {
  await signIn(page, "thapar", DEMO_TENANTS.thapar.owner);
  await page.goto(url("thapar", "/admin/academics"));
  const current = page.getByRole("button", { name: /2025-26/ });
  await expect(current).toContainText("Current");
  await expect(page.getByRole("cell", { name: "Odd semester ODD" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Even semester EVEN" })).toBeVisible();
});
