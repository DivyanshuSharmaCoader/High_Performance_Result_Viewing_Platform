/**
 * The training series' recordings, in order: each module continues the fictional Sunrise Public School
 * from the one before. Every step is done through the real interface; assertions check the real result
 * on screen, so a recording only exists if the workflow worked.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";

import { apiAs, latestEmail, linkFrom, url } from "../../e2e/support";
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
    await lesson.click(page.getByRole("button", { name: "New session" }).first());
    dialog = page.getByRole("dialog");
    await lesson.type(dialog.getByLabel("Code"), "2026-27");
    await lesson.type(dialog.getByLabel("Name"), "Academic year 2026–27");
  });
  await lesson.beat("dates", async () => {
    await lesson.point(dialog.getByLabel("Starts on"));
    await dialog.getByLabel("Starts on").fill("2026-04-01");
    await lesson.point(dialog.getByLabel("Ends on"));
    await dialog.getByLabel("Ends on").fill("2027-03-31");
    const current = dialog.getByRole("checkbox", { name: "Make this the current session" });
    await expect(current).toBeChecked(); // ticked by default
    await lesson.point(current);
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
    await expect(page.getByRole("cell", { name: "10A" }).first()).toBeVisible();
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

const EXAM = "Periodic Test 1 — October 2026";

test("m08-exam-setup", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m08-exam-setup");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro");
  let dialog = page.getByRole("dialog");
  await lesson.beat("open", async () => {
    await lesson.click(nav.getByRole("link", { name: "Exams" }));
    await lesson.click(page.getByRole("button", { name: "New exam" }).first());
    dialog = page.getByRole("dialog");
  });
  await lesson.beat("name", async () => {
    await lesson.type(dialog.getByLabel("Name"), EXAM);
    await lesson.choose(dialog.getByLabel("Kind"), "unit_test");
  });
  await lesson.beat("term", async () => {
    await lesson.point(dialog.getByLabel("Term"));
    await expect(dialog.getByLabel("Grading scheme")).toContainText("Class 10 grading");
    await lesson.point(dialog.getByLabel("Grading scheme"));
  });
  await lesson.beat("cohort", async () => {
    await lesson.click(dialog.getByText("10A — Class 10 · Section A"));
    await lesson.click(dialog.getByRole("button", { name: "Create exam" }));
    await expect(page.getByRole("heading", { name: EXAM })).toBeVisible();
  });
  await lesson.beat("draft", async () => {
    await expect(page.getByText("Draft", { exact: true })).toBeVisible();
    await lesson.point(page.getByRole("list", { name: "Readiness" }));
  });
  let paper = page.getByRole("dialog");
  await lesson.beat("paper", async () => {
    await lesson.click(page.getByRole("button", { name: "Add paper" }).first());
    paper = page.getByRole("dialog");
    await lesson.choose(paper.getByLabel("Course", { exact: true }), { label: "MATH10 — Mathematics" });
  });
  await lesson.beat("components", async () => {
    await lesson.click(paper.getByRole("button", { name: "Internal 40 + External 60" }));
    await lesson.type(paper.getByLabel("Component 2 code"), "WR");
    await lesson.type(paper.getByLabel("Component 2 name"), "Written");
  });
  await lesson.beat("total", async () => {
    await expect(paper.getByText("Paper total:")).toContainText("100");
    await lesson.point(paper.getByText("Paper total:"));
    await lesson.click(paper.getByRole("button", { name: "Add paper" }));
    await expect(page.getByRole("list", { name: "Papers" })).toContainText("MATH10");
  });
  await lesson.beat("more_papers", async () => {
    for (const label of ["SCI10 — Science", "ENG10 — English", "HIN10 — Hindi", "SST10 — Social Science"]) {
      await page.getByRole("button", { name: "Add paper" }).first().click();
      const d = page.getByRole("dialog");
      await d.getByLabel("Course", { exact: true }).selectOption({ label });
      await d.getByRole("button", { name: "Internal 40 + External 60" }).click();
      await d.getByLabel("Component 2 code").fill("WR");
      await d.getByLabel("Component 2 name").fill("Written");
      await d.getByRole("button", { name: "Add paper" }).click();
      await expect(d).toBeHidden();
    }
    await expect(page.getByRole("list", { name: "Papers" }).getByRole("listitem")).toHaveCount(5);
    await lesson.point(page.getByRole("list", { name: "Papers" }));
  });
  await lesson.beat("faculty", async () => {
    await lesson.click(page.getByRole("button", { name: "Actions for MATH10" }));
    await lesson.click(page.getByRole("menuitem", { name: "Assign faculty" }));
    const d = page.getByRole("dialog");
    await lesson.click(d.getByText(SCHOOL.teacherName).first());
    await lesson.click(d.getByRole("button", { name: "Save" }));
    await expect(d).toBeHidden();
    await expect(page.getByRole("list", { name: "Papers" })).toContainText(`10A: ${SCHOOL.teacherName}`);
  });
  await lesson.beat("open_entry", async () => {
    await lesson.click(page.getByRole("button", { name: "Open marks entry" }));
    await lesson.click(page.getByRole("dialog").getByRole("button", { name: "Open marks entry" }));
    await expect(page.getByText("Marks entry open", { exact: true })).toBeVisible();
  });
  await lesson.beat("outro");
  await lesson.finish();
});

/** Marks (Internal out of 40, Written out of 60) for Class 10-A; "AB" is absent. Made up for the series. */
const MARKS: Record<string, Record<string, [string, string]>> = {
  MATH10: {
    SPS1001: ["36", "52"],
    SPS1002: ["38", "55"],
    SPS1003: ["AB", ""],
    SPS1004: ["30", "44"],
    SPS1005: ["12", "14"],
    SPS1006: ["27", "41"],
  },
  SCI10: {
    SPS1001: ["34", "50"],
    SPS1002: ["37", "54"],
    SPS1003: ["25", "35"],
    SPS1004: ["31", "46"],
    SPS1005: ["18", "22"],
    SPS1006: ["29", "43"],
  },
  ENG10: {
    SPS1001: ["35", "48"],
    SPS1002: ["38", "56"],
    SPS1003: ["28", "38"],
    SPS1004: ["33", "49"],
    SPS1005: ["22", "30"],
    SPS1006: ["30", "45"],
  },
  HIN10: {
    SPS1001: ["33", "45"],
    SPS1002: ["36", "52"],
    SPS1003: ["30", "40"],
    SPS1004: ["34", "50"],
    SPS1005: ["24", "33"],
    SPS1006: ["31", "44"],
  },
  SST10: {
    SPS1001: ["32", "47"],
    SPS1002: ["35", "53"],
    SPS1003: ["26", "36"],
    SPS1004: ["32", "48"],
    SPS1005: ["20", "27"],
    SPS1006: ["28", "42"],
  },
};
const csvOf = (course: string, fix: Record<string, [string, string]> = {}) =>
  [
    "Enrollment No,Internal,Written",
    ...Object.entries({ ...MARKS[course]!, ...fix }).map(([e, [i, w]]) => `${e},${i},${w}`),
  ].join("\n");

/** A signed-in owner page off camera, for set-up the narration says was done the same way. */
async function ownerPage(browser: Browser, slug: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(url(slug, "/login"));
  await page.getByLabel("Email or enrollment number").fill(SCHOOL.ownerEmail);
  await page.getByLabel("Password", { exact: true }).fill(SCHOOL.ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
  return page;
}

test("m09-marks-entry", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m09-marks-entry");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.teacherEmail, SCHOOL.teacherPassword);
  await expect(page).toHaveURL(url(slug, "/marking"));
  await lesson.beat("intro");
  await lesson.beat("home", async () => {
    await lesson.point(page.getByRole("link", { name: /MATH10 · 10A/ }));
  });
  const grid = page.getByRole("table", { name: "Marks" });
  const cell = (enrollment: string, component: string) =>
    grid.getByRole("textbox", { name: `${enrollment} ${component}` });
  await lesson.beat("open", async () => {
    await lesson.click(page.getByRole("link", { name: /MATH10 · 10A/ }));
    await expect(grid).toBeVisible();
    await lesson.point(grid.getByRole("columnheader").filter({ hasText: "Written" }));
  });
  await lesson.beat("type", async () => {
    await lesson.type(cell("SPS1001", "Internal"), "36");
    await lesson.type(cell("SPS1001", "Written"), "52");
    await cell("SPS1001", "Written").press("Enter");
    await expect(grid.getByRole("row").nth(1)).toContainText("88");
    await lesson.point(grid.getByRole("row").nth(1));
  });
  await lesson.beat("invalid", async () => {
    await lesson.type(cell("SPS1002", "Internal"), "38");
    await lesson.type(cell("SPS1002", "Written"), "65");
    await expect(grid.getByText("Written: Out of 60")).toBeVisible();
    await lesson.point(grid.getByText("Written: Out of 60"));
  });
  await lesson.beat("fix", async () => {
    await lesson.type(cell("SPS1002", "Written"), "55");
    await expect(grid.getByText("Written: Out of 60")).toBeHidden();
  });
  await lesson.beat("absent", async () => {
    await lesson.type(cell("SPS1003", "Internal"), "AB");
  });
  await lesson.beat("paste", async () => {
    const block = ["SPS1004", "SPS1005", "SPS1006"].map((e) => MARKS.MATH10![e]!.join("\t")).join("\n");
    await lesson.point(cell("SPS1004", "Internal"));
    await cell("SPS1004", "Internal").evaluate((el, text) => {
      const data = new DataTransfer();
      data.setData("text/plain", text + "\n");
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
    }, block);
    await expect(cell("SPS1006", "Written")).toHaveValue("41");
  });
  await lesson.beat("saved", async () => {
    await expect(page.getByRole("status")).toHaveText("All changes saved", { timeout: 15_000 });
    await lesson.point(page.getByRole("status"));
  });
  await lesson.beat("submit", async () => {
    await lesson.click(page.getByRole("button", { name: "Submit paper" }));
    await lesson.click(page.getByRole("dialog").getByRole("button", { name: "Submit paper" }));
    await expect(page.getByText("Submitted", { exact: true }).first()).toBeVisible();
  });
  await lesson.beat("switch", async () => {
    await lesson.click(page.getByRole("button", { name: "Account menu" }));
    await lesson.click(page.getByRole("menuitem", { name: "Sign out" }));
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email or enrollment number").fill(SCHOOL.ownerEmail);
    await page.getByLabel("Password", { exact: true }).fill(SCHOOL.ownerPassword);
    await lesson.click(page.getByRole("button", { name: "Sign in" }));
    await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
  });
  let dialog = page.getByRole("dialog");
  await lesson.beat("import_open", async () => {
    await lesson.click(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Marks entry" }),
    );
    await lesson.click(page.getByRole("link", { name: /SCI10 · 10A/ }));
    await lesson.click(page.getByRole("button", { name: "Import from Excel" }));
    dialog = page.getByRole("dialog", { name: /Import SCI10 marks for 10A/ });
    await lesson.point(dialog.getByRole("link", { name: "Download template" }));
  });
  await lesson.beat("import_bad", async () => {
    await dialog.locator('input[type="file"]').setInputFiles({
      name: "science-10a.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csvOf("SCI10", { SPS1001: ["45", "50"] })),
    });
    await expect(page).toHaveURL(/\/admin\/imports\/[\w-]+$/);
    await expect(page.getByText("Ready to review")).toBeVisible({ timeout: 30_000 });
    const problem = page.getByRole("table").getByText(/Internal: 45 is outside 0–40/);
    await expect(problem).toBeVisible();
    await lesson.point(problem);
  });
  await lesson.beat("import_fix", async () => {
    await lesson.click(page.getByRole("button", { name: "Upload fixed file" }));
    await page
      .getByRole("dialog")
      .locator('input[type="file"]')
      .setInputFiles({
        name: "science-10a-fixed.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(csvOf("SCI10")),
      });
    const summary = page.getByText("Saves marks for 6 students");
    await expect(summary).toBeVisible({ timeout: 30_000 });
    await lesson.point(summary);
  });
  await lesson.beat("import_save", async () => {
    await lesson.click(page.getByRole("button", { name: "Import 6 rows" }));
    await lesson.click(
      page.getByRole("dialog", { name: "Save these marks?" }).getByRole("button", { name: "Save marks" }),
    );
    await expect(page.getByRole("heading", { name: "Marks saved" })).toBeVisible({ timeout: 30_000 });
  });
  await lesson.beat("outro");
  await lesson.finish();

  // Off camera, as the narration says: the other three subjects, entered the same way.
  const owner = await ownerPage(browser, slug);
  const work = await apiAs<{ exam_id: string; paper_id: string; cohort_id: string; course_code: string }[]>(
    owner,
    "GET",
    "/api/v1/marking",
  );
  for (const course of ["ENG10", "HIN10", "SST10"]) {
    const w = work.find((x) => x.course_code === course)!;
    const base = `/api/v1/exams/${w.exam_id}/papers/${w.paper_id}/cohorts/${w.cohort_id}/marks`;
    const sheet = await apiAs<{ students: { student_id: string; enrollment_no: string }[] }>(
      owner,
      "GET",
      base,
    );
    await apiAs(owner, "PUT", base, {
      changes: sheet.students.map((s) => {
        const [i, w2] = MARKS[course]![s.enrollment_no]!;
        return {
          student_id: s.student_id,
          attendance: "present",
          components: { INT: i, WR: w2 },
          version: null,
        };
      }),
    });
  }
  saveState({ examId: work[0]!.exam_id });
  await owner.context().close();
});

test("m10-results", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m10-results");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro", async () => {
    await lesson.click(nav.getByRole("link", { name: "Exams" }));
    await lesson.click(page.getByRole("link", { name: EXAM }));
    await expect(page.getByRole("heading", { name: EXAM })).toBeVisible();
  });
  await lesson.beat("close", async () => {
    await lesson.click(page.getByRole("button", { name: "Close marks entry" }));
    await lesson.click(page.getByRole("dialog").getByRole("button", { name: "Close marks entry" }));
    await expect(page.getByText("Marks entry closed", { exact: true })).toBeVisible();
  });
  await lesson.beat("results_tab", async () => {
    await lesson.click(
      page.getByRole("navigation", { name: "Exam sections" }).getByRole("link", { name: "Results" }),
    );
    const callout = page.getByText("Not every paper is submitted");
    await expect(callout).toBeVisible();
    await lesson.point(callout);
  });
  await lesson.beat("process", async () => {
    await lesson.click(page.getByRole("button", { name: "Process results" }));
    const d = page.getByRole("dialog", { name: "Process results?" });
    await lesson.type(
      d.getByRole("textbox"),
      "Science, English, Hindi and Social Science were entered by the office",
    );
    await lesson.click(d.getByRole("button", { name: "Process results" }));
    await expect(page.getByText(/Revision 1 · processed/)).toBeVisible({ timeout: 60_000 });
  });
  await lesson.beat("summary", async () => {
    await lesson.point(page.getByText(/Revision 1 · processed/));
    await lesson.point(page.getByRole("paragraph").filter({ hasText: /^Pass rate$/ }));
  });
  await lesson.beat("worth_a_look", async () => {
    const item = page.getByText("Processed before every paper was submitted");
    await expect(item).toBeVisible();
    await lesson.point(item);
  });
  await lesson.beat("preview", async () => {
    await lesson.click(page.getByRole("button", { name: SCHOOL.student.name }));
    const sheet = page.getByRole("dialog", { name: "Result preview" });
    await expect(sheet.getByRole("article")).toContainText(SCHOOL.student.enrollment);
    await lesson.point(sheet.getByRole("article"));
    await page.waitForTimeout(2500);
    await page.keyboard.press("Escape");
  });
  await lesson.beat("approve", async () => {
    await lesson.click(page.getByRole("button", { name: "Approve results" }));
    await lesson.click(
      page
        .getByRole("dialog", { name: "Approve revision 1?" })
        .getByRole("button", { name: "Approve results" }),
    );
    await expect(page.getByText(/approved revision 1 on/)).toBeVisible({ timeout: 20_000 });
  });
  await lesson.beat("schedule", async () => {
    const schedule = page.getByRole("button", { name: "Schedule…" });
    await expect(schedule).toBeDisabled();
    await lesson.point(schedule);
  });
  await lesson.beat("publish", async () => {
    await lesson.click(page.getByRole("button", { name: "Publish now" }));
    await lesson.click(
      page
        .getByRole("dialog", { name: /Publish to 6 students now\?/ })
        .getByRole("button", { name: "Publish now" }),
    );
    await expect(page.getByText(/Live since/)).toBeVisible({ timeout: 20_000 });
  });
  await lesson.beat("marksheets", async () => {
    await lesson.point(page.getByText(/Live since/));
    await expect(page.getByText(/marksheets are ready to download/)).toBeVisible({ timeout: 120_000 });
    await lesson.point(page.getByText(/marksheets are ready to download/));
  });
  await lesson.beat("outro", async () => {
    await lesson.point(page.getByRole("button", { name: "Withdraw" }));
  });
  await lesson.finish();
});

test("m11-student-result", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m11-student-result");
  const { page } = lesson;
  await page.goto(url(slug, "/login"));
  await lesson.beat("intro", async () => {
    await lesson.type(page.getByLabel("Email or enrollment number"), SCHOOL.student.enrollment);
    await page.getByLabel("Password", { exact: true }).fill(SCHOOL.student.password);
    await lesson.click(page.getByRole("button", { name: "Sign in" }));
    await expect(page).toHaveURL(url(slug, "/me"));
  });
  await lesson.beat("bell", async () => {
    // The unread count is read when the page loads (never polled): reload until the worker has sent it.
    const bell = page.getByRole("button", { name: /^Notifications, \d+ unread$/ });
    await expect(async () => {
      await page.reload();
      await expect(bell).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 60_000 });
    await lesson.click(bell);
    const note = page.getByRole("button", { name: new RegExp(`${EXAM} results are available`) }).first();
    await expect(note).toBeVisible();
    await lesson.point(note);
    await page.keyboard.press("Escape");
  });
  const latest = page.getByRole("link", { name: /Latest result/ });
  await lesson.beat("latest", async () => {
    await expect(latest).toContainText(EXAM);
    await lesson.point(latest);
  });
  await lesson.beat("open", async () => {
    await lesson.click(latest);
    const result = page.getByRole("article", { name: `Result of ${SCHOOL.student.name}` });
    await expect(result).toContainText("Mathematics");
    await lesson.point(result.getByText("Percentage").first());
    await lesson.point(result.getByRole("region", { name: "Marks by paper" }));
  });
  await lesson.beat("language", async () => {
    await lesson.choose(page.getByRole("combobox", { name: "Language" }), "hi");
    await expect(page.getByRole("region", { name: "अंक-पत्र (PDF)" })).toBeVisible();
    await page.waitForTimeout(2500);
    await page.getByRole("combobox", { name: "भाषा" }).selectOption("en");
  });
  const card = page.getByRole("region", { name: "Marksheet (PDF)" });
  await lesson.beat("marksheet", async () => {
    await lesson.point(card);
    const download = page.waitForEvent("download");
    await lesson.click(card.getByRole("button", { name: "Download" }));
    expect((await download).suggestedFilename()).toMatch(/^Marksheet-SPS1001-.+\.pdf$/);
  });
  let verifyUrl = "";
  await lesson.beat("share", async () => {
    await lesson.point(card.locator("code"));
    verifyUrl = `http://${await card.locator("code").textContent()}`;
  });
  await lesson.beat("verify", async () => {
    await page.goto(verifyUrl);
    await expect(page.getByRole("heading", { name: "Valid" })).toBeVisible();
    await expect(page.locator("main")).not.toContainText(SCHOOL.student.enrollment);
    await lesson.point(page.getByRole("heading", { name: "Valid" }));
  });
  await lesson.beat("parents");
  await lesson.beat("outro");
  await lesson.finish();
});

test("m12-plan-settings", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m12-plan-settings");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro");
  await lesson.beat("plan", async () => {
    await lesson.click(nav.getByRole("link", { name: "Plan & usage" }));
    await expect(page.getByText("Free", { exact: true }).first()).toBeVisible();
    await lesson.point(page.getByText("Free", { exact: true }).first());
  });
  await lesson.beat("usage", async () => {
    await lesson.point(page.getByRole("heading", { name: "Usage" }));
    await lesson.point(page.getByText("Active students").first());
  });
  await lesson.beat("compare", async () => {
    await lesson.point(page.getByRole("heading", { name: "Compare plans" }));
  });
  await lesson.beat("trial", async () => {
    const trial = page.getByRole("region", { name: /Try everything in Pro/ });
    await lesson.point(trial);
    await lesson.point(trial.getByRole("button", { name: "Start my free trial" }));
  });
  await lesson.beat("settings", async () => {
    await lesson.click(nav.getByRole("link", { name: "Settings" }));
    await lesson.point(page.getByLabel("Official name"));
    await lesson.point(page.getByLabel("Address"));
  });
  await lesson.beat("affiliation", async () => {
    await lesson.type(page.getByLabel("Affiliation"), "CBSE");
    await lesson.click(page.getByRole("button", { name: "Save changes" }));
    await expect(page.getByText("Settings saved")).toBeVisible();
  });
  await lesson.beat("policy", async () => {
    await lesson.point(page.getByRole("heading", { name: "Results policy" }));
    await lesson.point(page.getByLabel("Verification page"));
    await lesson.point(page.getByLabel("Language for students and marksheets"));
  });
  await lesson.beat("branding", async () => {
    await lesson.click(
      page.getByRole("navigation", { name: "Settings sections" }).getByRole("link", { name: "Branding" }),
    );
    // A made-up logo for the made-up school: an orange sun on white, drawn here.
    const png = await page.evaluate(() => {
      const c = document.createElement("canvas");
      c.width = c.height = 256;
      const g = c.getContext("2d")!;
      g.fillStyle = "#fff";
      g.fillRect(0, 0, 256, 256);
      g.fillStyle = "#ea580c";
      g.beginPath();
      g.arc(128, 150, 70, Math.PI, 0);
      g.fill();
      g.fillRect(40, 160, 176, 14);
      g.font = "bold 34px sans-serif";
      g.textAlign = "center";
      g.fillText("SUNRISE", 128, 222);
      return c.toDataURL("image/png").split(",")[1]!;
    });
    await lesson.point(page.getByRole("button", { name: /Choose a file/ }));
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: /Choose a file/ }).click();
    await (
      await chooser
    ).setFiles({ name: "sunrise-logo.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
    await expect(page.getByText("Logo updated")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Remove logo" })).toBeVisible();
  });
  await lesson.beat("theme", async () => {
    await lesson.point(page.getByText("Available on Starter and above").first());
  });
  await lesson.beat("outro");
  await lesson.finish();
});

test("m13-audit-export", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m13-audit-export");
  const { page } = lesson;
  await signInAs(lesson, slug, SCHOOL.ownerEmail, SCHOOL.ownerPassword);
  const nav = page.getByRole("navigation", { name: "Main" });
  await lesson.beat("intro");
  await lesson.beat("open", async () => {
    await lesson.click(nav.getByRole("link", { name: "Audit log" }));
    await expect(page.getByRole("button", { name: "Show details" }).first()).toBeVisible();
  });
  await lesson.beat("filter", async () => {
    await lesson.choose(page.getByLabel("Filter activity"), "marks.");
    await expect(page.getByRole("button", { name: "Show details" }).first()).toBeVisible();
  });
  await lesson.beat("person", async () => {
    await lesson.chooseContaining(page.getByLabel("Filter by person"), SCHOOL.teacherName);
    await expect(page.getByRole("button", { name: "Show details" }).first()).toBeVisible();
  });
  await lesson.beat("entry", async () => {
    await lesson.click(page.getByRole("button", { name: "Show details" }).first());
    const changed = page.getByRole("table", { name: "What changed" });
    await expect(changed).toBeVisible();
    await lesson.point(changed);
  });
  await lesson.beat("results", async () => {
    await page.getByLabel("Filter by person").selectOption("");
    await lesson.choose(page.getByLabel("Filter activity"), "results.");
    await expect(page.getByRole("button", { name: "Show details" }).first()).toBeVisible();
  });
  await lesson.beat("export", async () => {
    await lesson.click(nav.getByRole("link", { name: "Settings" }));
    await lesson.click(
      page.getByRole("navigation", { name: "Settings sections" }).getByRole("link", { name: "Your data" }),
    );
    await lesson.click(page.getByRole("button", { name: "Export everything" }));
  });
  await lesson.beat("ready", async () => {
    await expect(async () => {
      await page.reload();
      await expect(page.getByRole("button", { name: "Download" })).toBeVisible({ timeout: 3_000 });
    }).toPass({ timeout: 90_000 });
    await lesson.point(page.getByRole("button", { name: "Download" }));
  });
  await lesson.beat("outro");
  await lesson.finish();
});

test("m14-troubleshooting", async ({ browser }) => {
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m14-troubleshooting");
  const { page } = lesson;
  await page.goto(url(slug, "/login"));
  await lesson.beat("intro");
  await lesson.beat("wrong_password", async () => {
    await lesson.type(page.getByLabel("Email or enrollment number"), SCHOOL.student.enrollment);
    await page.getByLabel("Password", { exact: true }).fill("not-the-right-one");
    await lesson.click(page.getByRole("button", { name: "Sign in" }));
    const hint = page.getByText(/Check your login details/);
    await expect(hint).toBeVisible();
    await lesson.point(hint);
  });
  await lesson.beat("forgot", async () => {
    await lesson.point(page.getByRole("link", { name: "Forgot password?" }));
  });
  await lesson.beat("bad_code", async () => {
    await lesson.click(page.getByRole("link", { name: "Activate your student account" }));
    await lesson.type(page.getByLabel("Enrollment / roll number"), "SPS1002");
    await lesson.type(page.getByLabel("Activation code"), "ABCDE-23456");
    await page.getByLabel("New password").fill("priya-training-2026");
    await page.getByLabel("Confirm password").fill("priya-training-2026");
    await lesson.click(page.getByRole("button", { name: "Activate and sign in" }));
    const problem = page.getByText(/don't match an account waiting for activation/);
    await expect(problem).toBeVisible();
    await lesson.point(problem);
  });
  await lesson.beat("no_papers", async () => {
    await page.goto(url(slug, "/login"));
    await page.getByLabel("Email or enrollment number").fill(SCHOOL.teacherEmail);
    await page.getByLabel("Password", { exact: true }).fill(SCHOOL.teacherPassword);
    await page.getByRole("button", { name: "Sign in" }).click();
    const empty = page.getByText("Nothing to mark right now");
    await expect(empty).toBeVisible({ timeout: 20_000 });
    await lesson.point(empty);
  });
  await lesson.beat("limits", async () => {
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email or enrollment number").fill(SCHOOL.ownerEmail);
    await page.getByLabel("Password", { exact: true }).fill(SCHOOL.ownerPassword);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
    await lesson.click(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Plan & usage" }),
    );
    await lesson.point(page.getByText("Active students").first());
  });
  await lesson.beat("recap", async () => {
    const menu = page.getByRole("navigation", { name: "Main" });
    for (const name of ["Structure", "Grading", "Students", "Staff", "Exams", "Marks entry"]) {
      await lesson.point(menu.getByRole("link", { name }));
    }
  });
  await lesson.beat("outro");
  await lesson.finish();
});

test("m01-orientation", async ({ browser }) => {
  // Recorded last, so the tour shows a school that is already set up.
  const slug = state().slug!;
  const lesson = await Lesson.start(browser, "m01-orientation");
  const { page } = lesson;
  await page.goto(url(slug, "/login"));
  await lesson.beat("intro");
  await lesson.beat("school", async () => {
    await lesson.point(page.getByText(SCHOOL.name).first());
  });
  await lesson.beat("roles");
  await lesson.beat("no_parent");
  await lesson.beat("dashboard", async () => {
    await lesson.type(page.getByLabel("Email or enrollment number"), SCHOOL.ownerEmail);
    await page.getByLabel("Password", { exact: true }).fill(SCHOOL.ownerPassword);
    await lesson.click(page.getByRole("button", { name: "Sign in" }));
    await expect(page).toHaveURL(url(slug, "/admin"), { timeout: 20_000 });
  });
  await lesson.beat("menu", async () => {
    await lesson.point(page.getByRole("navigation", { name: "Main" }));
  });
  await lesson.beat("outro");
  await lesson.finish();
});
