import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

import { DEMO_TENANTS, apiAs, inviteFaculty, openMarksExam, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;

type Exam = Awaited<ReturnType<typeof openMarksExam>>;

async function roster(admin: Page, exam: Exam): Promise<string[]> {
  const sheet = await apiAs<{ students: { enrollment_no: string }[] }>(
    admin,
    "GET",
    `/api/v1/exams/${exam.examId}/papers/${exam.paperId}/cohorts/${exam.cohortId}/marks`,
  );
  return sheet.students.map((s) => s.enrollment_no);
}

const csv = (lines: string[]) => ({
  name: "ucs310-marks.csv",
  mimeType: "text/csv",
  buffer: Buffer.from(["Enrollment No,Internal,External", ...lines].join("\n")),
});

test("P8.5/P8.6: an administrator downloads the template, imports a file with an error, and the grid shows the rest", async ({
  page,
}) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await openMarksExam(page);
  const [a, b, c] = await roster(page, exam);
  await page.goto(url(THAPAR.slug, exam.sheet));
  await page.getByRole("button", { name: "Import from Excel" }).click();
  const dialog = page.getByRole("dialog", { name: /Import UCS310 marks for COE-2B/ });

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    dialog.getByRole("link", { name: "Download template" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/UCS310.*\.xlsx$/);
  expect((await readFile((await download.path())!)).subarray(0, 2).toString()).toBe("PK"); // a workbook

  await dialog.locator('input[type="file"]').setInputFiles(csv([`${a},45,50`, `${b},31,52`, `${c},AB,`]));
  await expect(page).toHaveURL(/\/admin\/imports\/[\w-]+$/);
  await expect(page.getByText("Ready to review")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("table").getByText(/Internal: 45 is outside 0–40/)).toBeVisible();
  await expect(page.getByText("Saves marks for 2 students: 2 new.")).toBeVisible();

  await page.getByRole("button", { name: "Import 2 valid rows" }).click();
  await page
    .getByRole("dialog", { name: "Save these marks?" })
    .getByRole("button", { name: "Save marks" })
    .click();
  await expect(page.getByRole("heading", { name: "Marks saved" })).toBeVisible({ timeout: 20_000 });

  await page.goto(url(THAPAR.slug, exam.sheet));
  const grid = page.getByRole("table", { name: "Marks" });
  await expect(grid.getByRole("textbox", { name: `${b} Internal` })).toHaveValue("31");
  await expect(grid.getByRole("textbox", { name: `${b} External` })).toHaveValue("52");
  await expect(grid.getByRole("textbox", { name: `${c} Internal` })).toHaveValue("AB");
  await expect(grid.getByRole("textbox", { name: `${a} Internal` })).toHaveValue(""); // the row with the error
});

test("P8.5: faculty import marks for their own paper, review them under Marks entry, and can submit", async ({
  page,
  browser,
}) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await openMarksExam(page);
  const faculty = await inviteFaculty(page, browser, THAPAR.slug);
  await apiAs(page, "PUT", `/api/v1/admin/exams/${exam.examId}/papers/${exam.paperId}/assignments`, {
    cohort_id: exam.cohortId,
    user_ids: [faculty.id],
  });
  const students = await roster(page, exam);
  const f = faculty.page;

  await f.goto(url(THAPAR.slug, "/marking"));
  await f.getByRole("link", { name: /UCS310 · COE-2B/ }).click();
  const grid = f.getByRole("table", { name: "Marks" });
  await expect(grid.getByRole("textbox", { name: `${students[0]} Internal` })).toHaveValue("");

  await f.getByRole("button", { name: "Import from Excel" }).click();
  await f
    .getByRole("dialog")
    .locator('input[type="file"]')
    .setInputFiles(csv(students.map((s, i) => `${s},${20 + (i % 20)},${30 + (i % 30)}`)));
  await expect(f).toHaveURL(/\/marking\/imports\/[\w-]+$/); // faculty have no admin area
  await expect(f.getByText("Ready to review")).toBeVisible({ timeout: 20_000 });
  await expect(
    f.getByText(`Saves marks for ${students.length} students: ${students.length} new.`),
  ).toBeVisible();
  await f.getByRole("button", { name: `Import ${students.length} rows` }).click();
  await f
    .getByRole("dialog", { name: "Save these marks?" })
    .getByRole("button", { name: "Save marks" })
    .click();
  await expect(f.getByRole("heading", { name: "Marks saved" })).toBeVisible({ timeout: 20_000 });

  // Back through the app (not a reload): the cached sheet must show the imported marks.
  await f.getByRole("link", { name: "Open marks entry" }).click();
  await f.getByRole("link", { name: /UCS310 · COE-2B/ }).click();
  await expect(grid.getByRole("textbox", { name: `${students[0]} Internal` })).toHaveValue("20");
  await expect(grid.getByRole("textbox", { name: `${students[1]} External` })).toHaveValue("31");
  await expect(f.getByRole("button", { name: "Submit paper" })).toBeEnabled();
  await faculty.close();
});
