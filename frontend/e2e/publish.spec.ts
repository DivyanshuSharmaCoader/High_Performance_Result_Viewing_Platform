import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_TENANTS, approvedQuiz, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;
const STUDENT = "102401001"; // the seeded student with an account, in COE-2A

test("P10: publish approved results; the student sees their own result on their phone", async ({
  page,
  browser,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await approvedQuiz(page, "COE-2A", { [STUDENT]: { INT: "34", EXT: "51" } });

  // The administrator publishes from the Results tab.
  await page.goto(url(THAPAR.slug, `/admin/exams/${exam.examId}/results`));
  await expect(page.getByText(/Approved and ready/)).toBeVisible();
  await page.getByRole("button", { name: "Publish now" }).click();
  await page
    .getByRole("dialog", { name: /Publish to \d+ students now\?/ })
    .getByRole("button", { name: "Publish now" })
    .click();
  await expect(page.getByText(/Live since/)).toBeVisible({ timeout: 15_000 });

  // The student, on a phone, sees exactly their own result.
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const phone = await context.newPage();
  await signIn(phone, THAPAR.slug, STUDENT, DEMO_PASSWORD);
  await expect(phone).toHaveURL(url(THAPAR.slug, "/me"));
  // The worker tells them in the app as well (the count is read on load, never polled).
  const bell = phone.getByRole("button", { name: /^Notifications, \d+ unread$/ });
  await expect(async () => {
    await phone.reload();
    await expect(bell).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await bell.click();
  await expect(phone.getByRole("button", { name: /Quiz .+ results are available/ }).first()).toBeVisible();
  await phone.keyboard.press("Escape");
  const latest = phone.getByRole("link", { name: /Latest result/ });
  await expect(latest).toContainText(/Quiz /);
  await expect(latest).toContainText("Passed");
  await latest.click();
  const result = phone.getByRole("article", { name: /Result of / });
  await expect(result).toContainText(STUDENT);
  await expect(result).toContainText("85%");
  await expect(
    result.getByText("Database Management Systems").locator("xpath=ancestor::li[1]"),
  ).toContainText("34 / 40");
  await context.close();
});
