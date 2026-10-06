import { expect, test, type Page } from "@playwright/test";

import { DEMO_TENANTS, apiAs, signIn, uniq, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;

async function openExam(page: Page): Promise<string> {
  const sessions = await apiAs<{ id: string; is_current: boolean }[]>(
    page,
    "GET",
    "/api/v1/admin/academic-sessions",
  );
  const session = sessions.find((s) => s.is_current)!;
  const terms = await apiAs<{ id: string }[]>(
    page,
    "GET",
    `/api/v1/admin/academic-sessions/${session.id}/terms`,
  );
  const cohorts = await apiAs<{ id: string; code: string }[]>(
    page,
    "GET",
    `/api/v1/admin/cohorts?session_id=${session.id}`,
  );
  const cohort = cohorts.find((c) => c.code === "COE-2B")!;
  const courses = await apiAs<{ items: { id: string; code: string }[] }>(
    page,
    "GET",
    "/api/v1/admin/courses?q=UCS310",
  );
  const exam = await apiAs<{ id: string }>(page, "POST", "/api/v1/admin/exams", {
    name: `Quiz ${uniq("")}`,
    kind: "unit_test",
    term_id: terms[0]!.id,
    cohort_ids: [cohort.id],
  });
  const withPaper = await apiAs<{ papers: { id: string }[] }>(
    page,
    "POST",
    `/api/v1/admin/exams/${exam.id}/papers`,
    {
      course_id: courses.items.find((c) => c.code === "UCS310")!.id,
      components: [
        { code: "INT", label: "Internal", max: "40" },
        { code: "EXT", label: "External", max: "60" },
      ],
    },
  );
  await apiAs(page, "POST", `/api/v1/admin/exams/${exam.id}/transitions`, { action: "open_entry" });
  return `/marking/${exam.id}/${withPaper.papers[0]!.id}/${cohort.id}`;
}

test("P8.3: enter marks with the keyboard, paste a block from Excel, and see a conflict", async ({
  page,
  browser,
}) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const sheet = await openExam(page);
  await page.goto(url(THAPAR.slug, sheet));
  const grid = page.getByRole("table", { name: "Marks" });
  const status = page.getByRole("status");

  // enter: type, Enter moves down, autosave
  const first = grid.getByRole("textbox", { name: /Internal$/ }).first();
  await first.fill("35");
  await first.press("Enter");
  await expect(grid.getByRole("textbox", { name: /Internal$/ }).nth(1)).toBeFocused();
  await grid
    .getByRole("textbox", { name: /External$/ })
    .first()
    .fill("52");
  await expect(status).toHaveText("All changes saved", { timeout: 10_000 });
  await expect(grid.getByRole("row").nth(1)).toContainText("87");

  // paste: a 2×2 block from the 2nd row
  await grid
    .getByRole("textbox", { name: /Internal$/ })
    .nth(1)
    .evaluate((el) => {
      const data = new DataTransfer();
      data.setData("text/plain", "30\t41\n12.5\t58\n");
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
    });
  await expect(grid.getByRole("textbox", { name: /External$/ }).nth(2)).toHaveValue("58");
  await expect(status).toHaveText("All changes saved", { timeout: 10_000 });
  await expect(grid.getByRole("row").nth(3)).toContainText("70.5");

  // conflict: a colleague saves the first row while this page still has the old version
  const other = await (await browser.newContext()).newPage();
  await signIn(other, THAPAR.slug, THAPAR.owner);
  await other.goto(url(THAPAR.slug, sheet));
  await other
    .getByRole("table", { name: "Marks" })
    .getByRole("textbox", { name: /Internal$/ })
    .first()
    .fill("38");
  await expect(other.getByRole("status")).toHaveText("All changes saved", { timeout: 10_000 });

  await first.fill("36");
  await expect(first).toHaveValue("38", { timeout: 10_000 }); // their value is loaded
  await expect(
    grid.getByText(/Someone else saved this row first\. Your entry \(36 \/ 52\) was not saved\./),
  ).toBeVisible();
  await other.context().close();
});
