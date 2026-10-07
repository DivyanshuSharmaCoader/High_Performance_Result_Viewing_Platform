import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_TENANTS, apiAs, openMarksExam, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;
const STUDENT = "102401001"; // the seeded student with an account, in COE-2A

test("P10: publish approved results; the student sees their own result on their phone", async ({
  page,
  browser,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await openMarksExam(page, "COE-2A");
  const base = `/api/v1/exams/${exam.examId}/papers/${exam.paperId}/cohorts/${exam.cohortId}/marks`;
  const sheet = await apiAs<{ students: { student_id: string; enrollment_no: string }[] }>(page, "GET", base);
  await apiAs(page, "PUT", base, {
    changes: sheet.students.map((s, i) => ({
      student_id: s.student_id,
      attendance: "present",
      components:
        s.enrollment_no === STUDENT
          ? { INT: "34", EXT: "51" }
          : { INT: String(15 + (i % 25)), EXT: String(25 + (i % 35)) },
      version: null,
    })),
  });
  const results = `/api/v1/admin/exams/${exam.examId}/results`;
  await apiAs(page, "POST", `/api/v1/admin/exams/${exam.examId}/transitions`, { action: "close_entry" });
  await apiAs(
    page,
    "POST",
    `${results}/process`,
    { override_reason: "E2E publish flow" },
    { "Idempotency-Key": crypto.randomUUID() },
  );
  await expect
    .poll(async () => (await apiAs<{ run: { status: string } }>(page, "GET", results)).run.status, {
      timeout: 30_000,
    })
    .toBe("completed");
  const run = await apiAs<{ run: { id: string } }>(page, "GET", results);
  await apiAs(page, "POST", `${results}/approve`, { run_id: run.run.id });

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
