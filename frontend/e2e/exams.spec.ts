import { expect, test } from "@playwright/test";

import { DEMO_TENANTS, signIn, uniq, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;

test("P7.6: set up an exam — cohorts, a paper with components — then open, close and reopen marks entry", async ({
  page,
}) => {
  const name = `End Semester ${uniq("")}`;
  await signIn(page, THAPAR.slug, THAPAR.owner);
  await page.goto(url(THAPAR.slug, "/admin/exams"));
  await page.getByRole("button", { name: "New exam" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Kind").selectOption("semester");
  await dialog.getByText("COE-2A — COE 2nd year · Group A").click();
  await dialog.getByRole("button", { name: "Create exam" }).click();

  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open marks entry" })).toBeDisabled(); // no papers yet

  await page.getByRole("button", { name: "Add paper" }).click();
  const paper = page.getByRole("dialog");
  await paper.getByLabel("Course", { exact: true }).selectOption({ label: "UCS301 — Data Structures" });
  await paper.getByRole("button", { name: "Mid-sem 25 + End-sem 45 + Sessionals 30" }).click();
  await paper.getByLabel("Component 2 minimum to pass").fill("18");
  await expect(paper.getByText("Paper total:")).toContainText("100");
  await paper.getByRole("button", { name: "Add paper" }).click();
  const papers = page.getByRole("list", { name: "Papers" });
  await expect(papers).toContainText("UCS301");
  await expect(papers).toContainText("End-semester 45 (min 18)");
  await expect(papers).toContainText("4 credits"); // copied from the course

  await page.getByRole("button", { name: "Open marks entry" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Open marks entry" }).click();
  await expect(page.getByText("Marks entry open", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Close marks entry" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Close marks entry" }).click();
  await expect(page.getByText("Marks entry closed", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Reopen marks entry" }).click();
  const reopen = page.getByRole("dialog");
  await reopen.getByRole("textbox").fill("Re-test for two students");
  await reopen.getByRole("button", { name: "Reopen marks entry" }).click();
  await expect(page.getByText("Marks entry open", { exact: true })).toBeVisible();

  await page.goto(url(THAPAR.slug, "/admin/exams"));
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText("Marks entry open");
});
