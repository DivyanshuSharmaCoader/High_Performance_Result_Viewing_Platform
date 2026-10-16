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
    await lesson.click(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Structure" }),
    );
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

test("m04-grading", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m04-grading");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro");
  let dialog = page.getByRole("dialog");
  await lesson.beat("open", async () => {
    await lesson.click(nav.getByRole("link", { name: "Grading" }));
    await expect(page.getByRole("heading", { name: "Grading", exact: true })).toBeVisible();
    await lesson.click(page.getByRole("button", { name: "New scheme" }).first());
    dialog = page.getByRole("dialog");
  });
  await lesson.beat("template", async () => {
    await lesson.click(dialog.getByText("9-band scale (CBSE-style)"));
  });
  await lesson.beat("name", async () => {
    await lesson.type(dialog.getByLabel("Name"), "Class 10 grading");
    await lesson.click(dialog.getByRole("button", { name: "Create scheme" }));
    await expect(page.getByRole("heading", { name: "Class 10 grading" })).toBeVisible();
  });
  await lesson.beat("bands", async () => {
    await lesson.point(page.getByText("A1", { exact: true }).first());
    await lesson.point(page.getByLabel("Pass mark per paper (%)", { exact: false }).first());
  });
  await lesson.beat("tryit", async () => {
    await lesson.point(page.getByRole("heading", { name: "Try it" }));
  });
  await lesson.beat("default", async () => {
    await lesson.click(nav.getByRole("link", { name: "Grading" }));
    const actions = page.getByRole("button", { name: "Actions for Class 10 grading" });
    await lesson.click(actions);
    const make = page.getByRole("menuitem", { name: "Make default" });
    if (await make.isVisible()) await lesson.click(make);
    else await page.keyboard.press("Escape");
    await lesson.point(page.getByText("Default").first());
  });
  await lesson.beat("versions");
  await lesson.beat("outro");
  await lesson.finish();
});

const STUDENTS_BAD = [
  "Enrollment no.,Full name,Cohort",
  "SPS1002,Priya Verma,10A",
  "SPS1003,Rohan Mehta,10A",
  "SPS1004,,10A",
  "SPS1003,Rohan Mehta,10A",
  "SPS1005,Kavya Iyer,10B",
].join("\n");
const STUDENTS_FIXED = [
  "Enrollment no.,Full name,Cohort",
  "SPS1002,Priya Verma,10A",
  "SPS1003,Rohan Mehta,10A",
  "SPS1004,Ananya Singh,10A",
  "SPS1005,Kavya Iyer,10A",
  "SPS1006,Vihaan Gupta,10A",
].join("\n");

test("m05-students", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m05-students");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro");
  let dialog = page.getByRole("dialog");
  await lesson.beat("open", async () => {
    await lesson.click(nav.getByRole("link", { name: "Students" }));
    await lesson.click(page.getByRole("button", { name: "Add student" }).first());
    dialog = page.getByRole("dialog");
  });
  await lesson.beat("fill", async () => {
    await lesson.type(dialog.getByLabel("Enrollment no."), SCHOOL.student.enrollment);
    await lesson.type(dialog.getByLabel("Full name"), SCHOOL.student.name);
  });
  await lesson.beat("cohort", async () => {
    await lesson.chooseContaining(dialog.getByLabel(/^Cohort/), "10A");
  });
  await lesson.beat("added", async () => {
    await lesson.click(dialog.getByRole("button", { name: "Add student" }));
    await expect(page.getByRole("heading", { name: /Aarav Sharma/ })).toBeVisible();
    await lesson.point(page.getByText("10A").first());
  });
  await lesson.beat("code", async () => {
    await lesson.click(page.getByRole("button", { name: "Issue activation code" }));
    const slip = page.getByRole("dialog");
    await expect(slip.getByText("Shown only now")).toBeVisible();
    const code = (await slip.locator("p.font-mono").first().textContent())?.trim() ?? "";
    expect(code).toMatch(/^[0-9A-Z]{5}-[0-9A-Z]{5}$/);
    saveState({ aaravCode: code });
    await lesson.point(slip.locator("p.font-mono").first());
    await page.waitForTimeout(1500);
    await lesson.click(slip.getByRole("button", { name: "Close" }));
  });
  await lesson.beat("import_intro", async () => {
    await lesson.click(nav.getByRole("link", { name: "Imports" }));
    await expect(page.getByRole("heading", { name: "Imports", exact: true })).toBeVisible();
  });
  await lesson.beat("upload_bad", async () => {
    await lesson.upload(
      page.getByRole("button", { name: /Choose a file/ }),
      "class-10a-students.csv",
      STUDENTS_BAD,
    );
    await expect(page).toHaveURL(/\/admin\/imports\/[0-9a-f-]+$/);
  });
  await lesson.beat("errors", async () => {
    const table = page.getByRole("table").first();
    await expect(table).toBeVisible({ timeout: 30_000 });
    await lesson.point(table);
    await expect(page.getByRole("button", { name: /^Import \d+ valid rows?$/ })).toBeVisible();
  });
  await lesson.beat("fix", async () => {
    await lesson.point(page.getByRole("link", { name: /Download checked file/ }));
    await lesson.click(page.getByRole("button", { name: "Upload fixed file" }));
    await lesson.upload(
      page.getByRole("dialog").getByRole("button", { name: /Choose a file/ }),
      "class-10a-students-fixed.csv",
      STUDENTS_FIXED,
    );
  });
  await lesson.beat("ready", async () => {
    const summary = page.getByText("5 new students will be added.");
    await expect(summary).toBeVisible({ timeout: 30_000 });
    await lesson.point(summary);
  });
  await lesson.beat("commit", async () => {
    await lesson.click(page.getByRole("button", { name: "Import 5 rows" }));
    await lesson.click(page.getByRole("dialog").getByRole("button", { name: "Import" }));
    await expect(page.getByRole("heading", { name: "Import complete" })).toBeVisible({ timeout: 30_000 });
  });
  await lesson.beat("done", async () => {
    await lesson.point(page.getByText(/5 added/));
    await lesson.click(page.getByRole("link", { name: "View students" }));
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(7); // header + Aarav + five
  });
  await lesson.beat("outro");
  await lesson.finish();
});

test("m06-staff", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m06-staff");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro");
  let dialog = page.getByRole("dialog");
  await lesson.beat("open", async () => {
    await lesson.click(nav.getByRole("link", { name: "Staff" }));
    await lesson.click(page.getByRole("button", { name: "Invite staff" }).first());
    dialog = page.getByRole("dialog");
  });
  await lesson.beat("fill", async () => {
    await lesson.type(dialog.getByLabel("Full name"), SCHOOL.teacherName);
    await lesson.type(dialog.getByLabel("Work email"), SCHOOL.teacherEmail);
  });
  await lesson.beat("role", async () => {
    await lesson.point(dialog.getByText("Administrator", { exact: true }));
    await lesson.click(dialog.getByText("Faculty", { exact: true }));
  });
  await lesson.beat("send", async () => {
    await lesson.click(dialog.getByRole("button", { name: "Send invitation" }));
    await expect(dialog).toBeHidden();
  });
  await lesson.beat("listed", async () => {
    await expect(page.getByText(SCHOOL.teacherName).first()).toBeVisible();
    await lesson.point(page.getByText(SCHOOL.teacherName).first());
  });
  await lesson.beat("accept", async () => {
    await lesson.click(page.getByRole("button", { name: "Account menu" }));
    await lesson.click(page.getByRole("menuitem", { name: "Sign out" }));
    await expect(page).toHaveURL(/\/login/);
    const mail = await latestEmail(SCHOOL.teacherEmail);
    await page.goto(linkFrom(mail.text, /http:\/\/\S+\/accept-invite\?token=[\w-]+/));
    await lesson.point(page.getByLabel("Password", { exact: true }));
    await page
      .getByLabel("Password", { exact: true })
      .pressSequentially(SCHOOL.teacherPassword, { delay: 35 });
    await page.getByLabel("Confirm password").pressSequentially(SCHOOL.teacherPassword, { delay: 35 });
    await lesson.click(page.getByRole("button", { name: "Create account" }));
    await expect(page).toHaveURL(url(slug, "/marking"), { timeout: 20_000 });
  });
  await lesson.beat("teacher_home", async () => {
    await lesson.point(page.getByRole("navigation", { name: "Main" }));
  });
  await lesson.beat("outro");
  await lesson.finish();
});

test("m07-student-activation", async ({ browser }) => {
  const { slug, aaravCode } = state();
  const lesson = await Lesson.start(browser, "m07-student-activation");
  const { page } = lesson;
  await page.goto(url(slug!, "/login"));
  await lesson.beat("intro");
  await lesson.beat("open", async () => {
    await lesson.click(page.getByRole("link", { name: "Activate your student account" }));
  });
  await lesson.beat("fill", async () => {
    await lesson.type(page.getByLabel("Enrollment / roll number"), SCHOOL.student.enrollment);
    await lesson.type(page.getByLabel("Activation code"), aaravCode!);
  });
  await lesson.beat("password", async () => {
    await lesson.point(page.getByLabel("New password"));
    await page.getByLabel("New password").pressSequentially(SCHOOL.student.password, { delay: 40 });
    await page.getByLabel("Confirm password").pressSequentially(SCHOOL.student.password, { delay: 40 });
  });
  await lesson.beat("activate", async () => {
    await lesson.click(page.getByRole("button", { name: "Activate and sign in" }));
    await expect(page).toHaveURL(/\/me$/, { timeout: 20_000 });
  });
  await lesson.beat("portal", async () => {
    await expect(page.getByRole("heading", { name: "Hello, Aarav" })).toBeVisible();
    await lesson.point(page.getByText("No results yet"));
  });
  await lesson.beat("signout", async () => {
    await lesson.click(page.getByRole("button", { name: "Account menu" }));
    await lesson.click(page.getByRole("button", { name: "Sign out" }));
    await expect(page).toHaveURL(/\/login/);
  });
  await lesson.beat("outro");
  await lesson.finish();
});
