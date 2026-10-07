import { expect, test } from "@playwright/test";

import { DEMO_TENANTS, marksCsv, openMarksExam, rosterOf, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;

test("Gate M4: marks with an error → fixed file → process → preview → approve, on the Thapar seed", async ({
  page,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await openMarksExam(page);
  const students = await rosterOf(page, exam);
  const good = students.map((s, i) => `${s},${20 + (i % 20)},${30 + (i % 30)}`);

  // 1. A file with a mistake: the check finds it, nothing is saved.
  await page.goto(url(THAPAR.slug, `/admin/imports?kind=marks&exam=${exam.examId}`));
  await page
    .locator('input[type="file"]')
    .setInputFiles(marksCsv([`${students[0]},55,40`, ...good.slice(1)]));
  // The hub lists everyone's recent imports (other tests run in parallel), so wait for this one's page.
  await expect(page).toHaveURL(/\/admin\/imports\/[\w-]+$/);
  await expect(page.getByText("Ready to review")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("table").getByText(/Internal: 55 is outside 0–40/)).toBeVisible();

  // 2. Fix it and upload again; this time everything imports.
  await page.getByRole("button", { name: "Upload fixed file" }).click();
  await page.getByRole("dialog").locator('input[type="file"]').setInputFiles(marksCsv(good, "fixed.csv"));
  await expect(page.getByText(`Saves marks for ${students.length} students`)).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: `Import ${students.length} rows` }).click();
  await page
    .getByRole("dialog", { name: "Save these marks?" })
    .getByRole("button", { name: "Save marks" })
    .click();
  await expect(page.getByRole("heading", { name: "Marks saved" })).toBeVisible({ timeout: 20_000 });

  // 3. Close marks entry, then process from the Results tab (the paper wasn't submitted: give a reason).
  await page.goto(url(THAPAR.slug, `/admin/exams/${exam.examId}`));
  await page.getByRole("button", { name: "Close marks entry" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Close marks entry" }).click();
  await expect(page.getByText("Marks entry is closed.", { exact: false }).first()).toBeVisible();
  await page
    .getByRole("navigation", { name: "Exam sections" })
    .getByRole("link", { name: "Results" })
    .click();
  await expect(page.getByText("Not every paper is submitted")).toBeVisible();
  await page.getByRole("button", { name: "Process results" }).click();
  const processDialog = page.getByRole("dialog", { name: "Process results?" });
  await processDialog.getByRole("textbox").fill("Marks were imported by the exam office");
  await processDialog.getByRole("button", { name: "Process results" }).click();

  // 4. Preview: figures, the anomaly list and one student's result as they will see it.
  await expect(page.getByText(/Revision 1 · processed/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(`${students.length} students:`, { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Processed before every paper was submitted")).toBeVisible();
  await expect(page.getByRole("paragraph").filter({ hasText: /^Pass rate$/ })).toBeVisible();
  const table = page.getByRole("table").filter({ has: page.getByRole("columnheader", { name: "Student" }) });
  await table.getByRole("button").first().click();
  const sheet = page.getByRole("dialog", { name: "Result preview" });
  await expect(sheet.getByRole("article")).toContainText("Internal");
  await expect(sheet.getByRole("article")).toContainText(students[0]!);
  await page.keyboard.press("Escape");

  // 5. Approve (a fresh sign-in counts as a recent password check); the marks lock.
  await page.getByRole("button", { name: "Approve results" }).click();
  await page
    .getByRole("dialog", { name: "Approve revision 1?" })
    .getByRole("button", { name: "Approve results" })
    .click();
  await expect(page.getByText(/approved revision 1 on/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Revoke approval" })).toBeVisible();

  await page.goto(url(THAPAR.slug, exam.sheet));
  await expect(page.getByText("Read only", { exact: true })).toBeVisible();
});
