import { expect, test } from "@playwright/test";

import { createTenantViaSignup, signIn, uniq, url } from "./support";

const PASSWORD = "an-e2e-owner-passphrase";

test("a new institution starts its one 30-day Pro trial and sees it everywhere", async ({
  page,
  request,
}) => {
  // A free-mail owner, so the institutional-domain signal doesn't tie test institutions together.
  const { slug, email } = await createTenantViaSignup(
    request,
    `Trial School ${uniq("")}`,
    `${uniq("head")}@gmail.com`,
  );
  await signIn(page, slug, email, PASSWORD);

  await page.goto(url(slug, "/admin/plan"));
  await expect(page.getByRole("heading", { name: "Try everything in Pro, free for 30 days" })).toBeVisible();
  const table = page.getByRole("table", { name: "Plans and what they include" });
  await expect(table.getByRole("columnheader", { name: /Free/ })).toContainText("Current");

  await page.getByRole("button", { name: "Start my free trial" }).click();
  const dialog = page.getByRole("dialog", { name: "Start your 30-day Pro trial?" });
  await expect(dialog).toContainText("nothing is charged and nothing is deleted");
  await dialog.getByRole("button", { name: "Start trial" }).click();

  await expect(page.getByText("30 days left in your Pro trial")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start my free trial" })).toHaveCount(0);
  await expect(table.getByRole("columnheader", { name: /Pro/ }).first()).toContainText("Your trial");

  // Every staff page carries the countdown, and a reload keeps the state (it lives on the server).
  await page.goto(url(slug, "/admin"));
  await expect(page.getByRole("status").filter({ hasText: "Pro trial: 30 days left." })).toBeVisible();
  await page.goto(url(slug, "/admin/plan"));
  await expect(page.getByText("30 days left in your Pro trial")).toBeVisible();
});
