import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_PLATFORM, DEMO_TENANTS, approvedQuiz, signIn, totp, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;

test("P13.2 + P13.4: an administrator drills into a paper and opens the exam's history", async ({ page }) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await approvedQuiz(page, "COE-2B");

  await page.goto(url(THAPAR.slug, `/admin/exams/${exam.examId}/results`));
  await expect(page.getByRole("heading", { name: "Distribution" })).toBeVisible();
  await expect(page.getByText(/spread ±\d/).first()).toBeVisible();
  await page.getByRole("button", { name: /^UCS310 .+: details$/ }).click();
  const sheet = page.getByRole("dialog", { name: /^UCS310 · / });
  await expect(sheet.getByRole("list", { name: "UCS310 students by percentage" })).toBeVisible();
  await expect(sheet.getByText(/of \d+ passed/)).toBeVisible();
  await page.keyboard.press("Escape");

  // The exam's own history in the audit log: approval, processing and setup, newest first.
  await page.getByRole("button", { name: "History" }).click();
  await expect(page).toHaveURL(/\/admin\/audit-log\?entity_id=/);
  await expect(page.getByText(/^History of Quiz /)).toBeVisible();
  // Each row shows what happened in words plus its stable code.
  for (const code of ["results.approved", "results.processed", "exam.open_entry", "exam.created"]) {
    await expect(page.getByText(code, { exact: true }).first()).toBeVisible();
  }
  await page.getByRole("button", { name: "Show all records" }).click();
  await expect(page).not.toHaveURL(/entity_id=/);
});

test("P13.5: the platform console shows fleet and result-day metrics", async ({ page }) => {
  await page.goto(url("admin", "/login"));
  await page.getByLabel("Work email").fill(DEMO_PLATFORM.email);
  await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByLabel("Authenticator code").fill(totp(DEMO_PLATFORM.totpSecret));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  // Tiles carry live numbers (the demo seed has institutions and students).
  await expect(page.getByText(/^\d+ new this week$/)).toBeVisible();
  await expect(page.getByText(/^\d+ published this week$/)).toBeVisible();
  for (const title of ["Institutions by status", "Institutions by plan", "Result day", "Background jobs"]) {
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }
  for (const label of ["Marksheets being prepared", "Marksheets failed", "Emails failed (7 days)"]) {
    await expect(page.getByText(label)).toBeVisible();
  }
  await expect(page.getByText("Server errors (5xx)")).toBeVisible();
  await expect(page.getByText("Redis cache hit rate")).toBeVisible();
});
