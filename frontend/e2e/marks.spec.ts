import { expect, test } from "@playwright/test";

import { DEMO_TENANTS, openMarksExam, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;

test("P8.3: enter marks with the keyboard, paste a block from Excel, and see a conflict", async ({
  page,
  browser,
}) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const { sheet } = await openMarksExam(page);
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
