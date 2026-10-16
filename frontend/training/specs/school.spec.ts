/**
 * The training series' recordings, in order: each module continues the fictional Sunrise Public School
 * from the one before. Every step is done through the real interface; assertions check the real result
 * on screen, so a recording only exists if the workflow worked.
 */
import { expect, test } from "@playwright/test";

import { latestEmail, linkFrom, url } from "../../e2e/support";
import { Lesson, SCHOOL, saveState, state } from "../support";

test.describe.configure({ mode: "serial" });

async function signInAs(lesson: Lesson, slug: string, login: string, password: string): Promise<void> {
  const { page } = lesson;
  await page.goto(url(slug, "/login"));
  await lesson.type(page.getByLabel("Email or enrollment number"), login);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await lesson.click(page.getByRole("button", { name: "Sign in" }));
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

test("m02-create-portal", async ({ browser }) => {
  const lesson = await Lesson.start(browser, "m02-create-portal");
  const { page } = lesson;
  await lesson.beat("intro", async () => {
    await page.goto(url("", "/"));
  });
  await lesson.beat("open", async () => {
    await page.goto(url("", "/signup"));
    await expect(page.getByLabel("Institution name")).toBeVisible();
  });
  await lesson.beat("name", async () => {
    await lesson.type(page.getByLabel("Institution name"), SCHOOL.name);
  });
  let slug = "";
  await lesson.beat("address", async () => {
    await lesson.point(page.getByLabel("Portal address"));
    slug = await page.getByLabel("Portal address").inputValue();
    await expect(page.getByText("Available")).toBeVisible();
    await lesson.point(page.getByText("Available"));
  });
  await lesson.beat("type", async () => {
    await lesson.choose(page.getByLabel("Type"), "school");
  });
  await lesson.beat("owner", async () => {
    await lesson.type(page.getByLabel("Your name"), SCHOOL.ownerName);
    await lesson.type(page.getByLabel("Work email"), SCHOOL.ownerEmail);
  });
  await lesson.beat("password", async () => {
    await lesson.point(page.getByLabel("Password", { exact: true }));
    await page.getByLabel("Password", { exact: true }).pressSequentially(SCHOOL.ownerPassword, { delay: 40 });
  });
  await lesson.beat("submit", async () => {
    await lesson.click(page.getByRole("button", { name: "Create portal" }));
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  });
  await lesson.beat("verify", async () => {
    const mail = await latestEmail(SCHOOL.ownerEmail);
    await page.goto(linkFrom(mail.text, /http:\/\/\S+\/signup\/verify\?token=[\w-]+/));
    await expect(page).toHaveURL(url(slug, "/admin"), { timeout: 20_000 });
  });
  await lesson.beat("landed", async () => {
    const checklist = page.getByRole("heading", { name: "Set up your institution" });
    await expect(checklist).toBeVisible();
    await lesson.point(checklist);
    await lesson.point(page.getByText(/^0 of \d+ steps done/));
  });
  await lesson.beat("plan");
  await lesson.beat("outro");
  saveState({ slug });
  await lesson.finish();
});

test("m03-academic-structure", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m03-academic-structure");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  await lesson.beat("intro");
  await lesson.beat("open", async () => {
    await lesson.click(page.getByRole("link", { name: "Structure" }));
    await expect(page).toHaveURL(url(slug, "/admin/academics"));
  });
  let dialog = page.getByRole("dialog");
  await lesson.beat("session", async () => {
    await lesson.click(page.getByRole("button", { name: /New academic session/ }).first());
    dialog = page.getByRole("dialog");
    await lesson.type(dialog.getByLabel("Code"), "2026-27");
    await lesson.type(dialog.getByLabel("Name"), "Academic year 2026–27");
  });
  await lesson.beat("dates", async () => {
    await lesson.point(dialog.getByLabel("Starts on"));
    await dialog.getByLabel("Starts on").fill("2026-04-01");
    await lesson.point(dialog.getByLabel("Ends on"));
    await dialog.getByLabel("Ends on").fill("2027-03-31");
    const current = dialog.getByText("Make this the current session");
    if (await current.isVisible()) await lesson.click(current);
  });
  await lesson.beat("create", async () => {
    await lesson.click(dialog.getByRole("button", { name: "Create session" }));
    await expect(page.getByRole("button", { name: /2026-27/ })).toContainText("Current");
  });
  await lesson.beat("term1", async () => {
    await lesson.click(page.getByRole("button", { name: "Add term" }).first());
    dialog = page.getByRole("dialog");
    await lesson.type(dialog.getByLabel("Code"), "T1");
    await lesson.type(dialog.getByLabel("Name"), "Term 1");
    await lesson.click(dialog.getByRole("button", { name: "Add term" }));
    await expect(page.getByRole("cell", { name: /Term 1/ })).toBeVisible();
  });
  await lesson.beat("term2", async () => {
    await lesson.click(page.getByRole("button", { name: "Add term" }).first());
    dialog = page.getByRole("dialog");
    await lesson.type(dialog.getByLabel("Code"), "T2");
    await lesson.type(dialog.getByLabel("Name"), "Term 2");
    await lesson.click(dialog.getByRole("button", { name: "Add term" }));
    await expect(page.getByRole("cell", { name: /Term 2/ })).toBeVisible();
  });
  const tabs = page.getByRole("navigation", { name: "Academic structure" });
  await lesson.beat("programs", async () => {
    await lesson.click(tabs.getByRole("link", { name: "Programs" }));
    await lesson.click(page.getByRole("button", { name: "New program" }).first());
  });
  await lesson.beat("program_fill", async () => {
    dialog = page.getByRole("dialog");
    await lesson.type(dialog.getByLabel("Code"), "C10");
    await lesson.type(dialog.getByLabel("Name"), "Class 10");
    await lesson.type(dialog.getByLabel(/^Level/), "Secondary");
    await lesson.click(dialog.getByRole("button", { name: "Create program" }));
    await expect(page.getByRole("cell", { name: "Class 10" })).toBeVisible();
  });
  await lesson.beat("cohorts", async () => {
    await lesson.click(tabs.getByRole("link", { name: "Cohorts" }));
    await lesson.click(page.getByRole("button", { name: "New cohort" }).first());
  });
  await lesson.beat("cohort_fill", async () => {
    dialog = page.getByRole("dialog");
    await lesson.choose(dialog.getByLabel("Session"), { label: "2026-27" });
    await lesson.choose(dialog.getByLabel("Program"), { label: "Class 10" });
    await lesson.type(dialog.getByLabel("Code"), "10A");
    await lesson.type(dialog.getByLabel("Name"), "Class 10 · Section A");
    await lesson.click(dialog.getByRole("button", { name: "Create cohort" }));
    await expect(page.getByRole("cell", { name: "10A" })).toBeVisible();
  });
  const course = async (code: string, name: string) => {
    await lesson.click(page.getByRole("button", { name: "New course" }).first());
    dialog = page.getByRole("dialog");
    await lesson.type(dialog.getByLabel("Code"), code);
    await lesson.type(dialog.getByLabel("Name"), name);
  };
  await lesson.beat("courses", async () => {
    await lesson.click(tabs.getByRole("link", { name: "Courses" }));
    await course("MATH10", "Mathematics");
  });
  await lesson.beat("credits", async () => {
    await lesson.point(dialog.getByLabel(/^Credits/));
    await lesson.click(dialog.getByRole("button", { name: "Create course" }));
    await expect(page.locator("[data-sonner-toast]").getByText("Course MATH10 created")).toBeVisible();
  });
  await lesson.beat("more_courses", async () => {
    for (const [code, name] of [
      ["SCI10", "Science"],
      ["ENG10", "English"],
      ["HIN10", "Hindi"],
      ["SST10", "Social Science"],
    ] as const) {
      await page.getByRole("button", { name: "New course" }).first().click();
      dialog = page.getByRole("dialog");
      await dialog.getByLabel("Code").fill(code);
      await dialog.getByLabel("Name").fill(name);
      await dialog.getByRole("button", { name: "Create course" }).click();
      await expect(page.getByRole("cell", { name }).first()).toBeVisible();
    }
  });
  await lesson.beat("outro", async () => {
    await expect(page.getByRole("row")).toHaveCount(6); // header + five subjects
  });
  await lesson.finish();
});
