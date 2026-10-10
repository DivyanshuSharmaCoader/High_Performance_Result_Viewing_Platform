import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_TENANTS, apiAs, approvedQuiz, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;
const STUDENT = "102401001"; // the seeded student with an account, in COE-2A

test("P18.3: correct published results; the live version stays until the corrected one replaces it", async ({
  page,
  browser,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await approvedQuiz(page, "COE-2A", { [STUDENT]: { INT: "34", EXT: "51" } });
  const pubs = `/api/v1/admin/exams/${exam.examId}/publications`;
  const v1 = await apiAs<{ id: string }>(page, "POST", pubs, {}, { "Idempotency-Key": crypto.randomUUID() });

  // Start the correction from the Results tab, with a reason.
  await page.goto(url(THAPAR.slug, `/admin/exams/${exam.examId}/results`));
  await page.getByRole("button", { name: "Correct results…" }).click();
  const start = page.getByRole("dialog", { name: "Correct the published results?" });
  await start.getByLabel(/What needs correcting/).fill(`${STUDENT}'s internal mark is 30, not 34`);
  await start.getByRole("button", { name: "Start correction" }).click();
  await expect(page.getByRole("heading", { name: "Correcting published results" })).toBeVisible();
  await expect(page.getByText("Students still see version 1")).toBeVisible();

  // Change the mark (administrators may, during a correction), then process and approve again.
  const marks = `/api/v1/exams/${exam.examId}/papers/${exam.paperId}/cohorts/${exam.cohortId}/marks`;
  const sheet = await apiAs<{
    students: { student_id: string; enrollment_no: string; entry: { version: number } | null }[];
  }>(page, "GET", marks);
  const row = sheet.students.find((s) => s.enrollment_no === STUDENT)!;
  await apiAs(page, "PUT", marks, {
    changes: [
      {
        student_id: row.student_id,
        attendance: "present",
        components: { INT: "30" },
        version: row.entry!.version,
      },
    ],
  });
  const results = `/api/v1/admin/exams/${exam.examId}/results`;
  await apiAs(
    page,
    "POST",
    `${results}/process`,
    { override_reason: null },
    { "Idempotency-Key": crypto.randomUUID() },
  );
  await expect
    .poll(async () => (await apiAs<{ run: { status: string } }>(page, "GET", results)).run.status, {
      timeout: 30_000,
    })
    .toBe("completed");

  // Before approving, the panel shows exactly who changes and how.
  await page.reload();
  await expect(page.getByText(/1 of \d+ students has a different result/)).toBeVisible();
  const change = page
    .getByRole("table", { name: "Students whose result changes" })
    .getByRole("row", { name: new RegExp(STUDENT) });
  await expect(change).toContainText("85%");
  await expect(change).toContainText("81%");

  const run = await apiAs<{ run: { id: string } }>(page, "GET", results);
  await apiAs(page, "POST", `${results}/approve`, { run_id: run.run.id });
  await page.reload();
  await page.getByRole("button", { name: "Publish corrected results" }).click();
  const confirm = page.getByRole("dialog", { name: "Replace version 1 with the corrected results?" });
  await expect(confirm).toContainText("1 student's result changes; only they are told");
  await confirm.getByRole("button", { name: "Publish corrected results" }).click();
  await expect(page.getByText(/Live since/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Correcting published results" })).toHaveCount(0);
  const listed = await apiAs<{ id: string; version: number; status: string }[]>(page, "GET", pubs);
  expect(listed.map((p) => [p.version, p.status])).toEqual([
    [2, "published"],
    [1, "superseded"],
  ]);

  // The student sees the corrected result, marked as revised; the replaced version is gone.
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const phone = await context.newPage();
  await signIn(phone, THAPAR.slug, STUDENT, DEMO_PASSWORD);
  await phone.goto(url(THAPAR.slug, `/me/results/${listed[0]!.id}`));
  const result = phone.getByRole("article", { name: /Result of / });
  await expect(result).toContainText("81%");
  const gone = await phone.evaluate(async (id) => (await fetch(`/api/v1/me/results/${id}`)).status, v1.id);
  expect(gone).toBe(404);
  await context.close();
});
