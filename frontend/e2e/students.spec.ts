import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_TENANTS, signIn, uniq, url } from "./support";

const COACHING = DEMO_TENANTS.democoaching;

async function uploadCsv(page: Page, name: string, csv: string) {
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: /Choose a file/ }).click();
  await (await chooser).setFiles({ name, mimeType: "text/csv", buffer: Buffer.from(csv) });
}

test("P6.6: import students with errors → upload the fixed file → commit", async ({ page }) => {
  const tag = uniq("E").toUpperCase().slice(0, 10);
  await signIn(page, COACHING.slug, COACHING.owner);
  await page.goto(url(COACHING.slug, "/admin/imports"));
  await expect(page.getByRole("heading", { name: "Imports", exact: true })).toBeVisible();

  await uploadCsv(
    page,
    "batch.csv",
    `Roll No,Student Name,Email,Section\n${tag}1,Ira Kapoor,ira@example.com,JEE-MA\n${tag}2,Kabir Shah,not-an-email,JEE-MA\n`,
  );
  await expect(page).toHaveURL(/\/admin\/imports\/[0-9a-f-]+$/);
  // Problems show as a table on desktop and as cards on phones; check the visible one.
  await expect(page.getByRole("table").getByText("“not-an-email” isn't a valid email address.")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("button", { name: "Import 1 valid row" })).toBeEnabled();
  const report = page.waitForEvent("download");
  await page.getByRole("link", { name: /Download checked file/ }).click();
  expect((await report).suggestedFilename()).toBe("batch - checked.xlsx");

  await page.getByRole("button", { name: "Upload fixed file" }).click();
  const chooser = page.waitForEvent("filechooser");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Choose a file/ })
    .click();
  await (
    await chooser
  ).setFiles({
    name: "batch-fixed.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      `Roll No,Student Name,Email,Section\n${tag}1,Ira Kapoor,ira@example.com,JEE-MA\n${tag}2,Kabir Shah,kabir@example.com,JEE-EB\n`,
    ),
  });
  await expect(page.getByText("2 new students will be added.")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Import 2 rows" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("heading", { name: "Import complete" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/2 added/)).toBeVisible();

  await page.getByRole("link", { name: "View students" }).click();
  await page.getByRole("searchbox", { name: "Search students" }).fill(tag);
  const table = page.getByRole("table");
  await expect(table.getByRole("row")).toHaveCount(3); // header + 2
  await expect(table.getByRole("row", { name: /Kabir Shah/ })).toContainText("JEE-EB");
});

test("P6.7: admin issues an activation code, the student activates, signs out and signs in again", async ({
  page,
  browser,
}) => {
  const enrollment = uniq("ACT").toUpperCase().slice(0, 12);
  await signIn(page, COACHING.slug, COACHING.owner);
  await page.goto(url(COACHING.slug, "/admin/students"));
  await page.getByRole("button", { name: "Add student" }).click();
  const add = page.getByRole("dialog");
  await add.getByLabel("Enrollment no.").fill(enrollment);
  await add.getByLabel("Full name").fill("Meher Gill");
  await add.getByRole("button", { name: "Add student" }).click();
  await expect(page.getByRole("heading", { name: /Meher Gill/ })).toBeVisible();

  await page.getByRole("button", { name: "Issue activation code" }).click();
  const slip = page.getByRole("dialog");
  await expect(slip.getByText("Shown only now")).toBeVisible();
  const code = (await slip.locator("p.font-mono").first().textContent())?.trim() ?? "";
  expect(code).toMatch(/^[0-9A-Z]{5}-[0-9A-Z]{5}$/);
  await slip.getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Code issued").first()).toBeVisible();

  const student = await (await browser.newContext()).newPage();
  await student.goto(url(COACHING.slug, "/activate"));
  await student.getByLabel("Enrollment / roll number").fill(enrollment.toLowerCase());
  await student.getByLabel("Activation code").fill(code.replace("-", " "));
  const password = `${uniq("meher")}-pass-phrase`; // generated per run: no fixed credential in the repo
  await student.getByLabel("New password").fill(password);
  await student.getByLabel("Confirm password").fill(password);
  await student.getByRole("button", { name: "Activate and sign in" }).click();
  await expect(student).toHaveURL(/\/me$/);
  await expect(student.getByRole("heading", { name: "Hello, Meher" })).toBeVisible();
  await expect(student.getByText("No results yet")).toBeVisible();

  await student.getByRole("button", { name: "Account menu" }).click();
  await student.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(student).toHaveURL(/\/login/);
  await signIn(student, COACHING.slug, enrollment, password);
  await expect(student).toHaveURL(/\/me$/);

  await page.reload();
  await expect(page.getByText("Activated").first()).toBeVisible();
});

test("P3.11: the seeded demo student signs in to the student portal, not the admin area", async ({
  page,
}) => {
  await signIn(page, "thapar", "102401001", DEMO_PASSWORD);
  await expect(page).toHaveURL(/\/me$/);
  await expect(page.getByText("Enrollment no. 102401001")).toBeVisible();
  await page.goto(url("thapar", "/admin/students"));
  await expect(
    page.getByRole("heading", { name: /don't have access|not allowed|permission/i }),
  ).toBeVisible();
});
