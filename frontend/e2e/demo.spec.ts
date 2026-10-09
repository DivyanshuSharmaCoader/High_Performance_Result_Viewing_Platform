import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { BASE, DEMO_PASSWORD, DEMO_PLATFORM, DEMO_TENANTS, PORT, apiAs, signIn, totp, url } from "./support";

/**
 * The presentation's demo script (docs/demo/README.md), run end to end (P17.1, P17.2). It needs the demo
 * history: `scorecode seed --with-history`, then E2E_DEMO=1 (the demo workflow does both). The steps
 * follow the script's order, so a failure names the step that would go wrong on stage.
 */
test.skip(!process.env.E2E_DEMO, "needs `scorecode seed --with-history` (demo.yml)");
// One stage, one run: each step builds on the previous one, so a retry would meet a changed world.
test.describe.configure({ mode: "serial", retries: 0 });

const THAPAR = DEMO_TENANTS.thapar;
const STUDENT = "102401001"; // COE-2A, the seeded student with an account
const FILES = fileURLToPath(new URL("../../docs/demo/files", import.meta.url));
const LIVE = "End semester examination, even 2026"; // approved by the seed, published on stage
const MIDSEM = "Mid-semester test, even 2026"; // open for marks entry

type ExamItem = { id: string; name: string; status: string };

async function examsOf(page: Page): Promise<ExamItem[]> {
  return apiAs<ExamItem[]>(page, "GET", "/api/v1/admin/exams");
}

test("1 · three institutions, one build, each with its own name and colours", async ({ page }) => {
  for (const t of Object.values(DEMO_TENANTS)) {
    await page.goto(url(t.slug, "/login"));
    await expect(page.getByText(t.name).first()).toBeVisible();
  }
});

test("2 · Thapar's exam office: history, one approved exam, one taking marks", async ({ page }) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const byName = Object.fromEntries((await examsOf(page)).map((e) => [e.name, e.status]));
  expect(byName).toMatchObject({
    "End semester examination, odd 2024": "published",
    "End semester examination, even 2025": "published",
    "End semester examination, odd 2025": "published",
    [LIVE]: "approved",
    [MIDSEM]: "marks_entry_open",
  });
  await page.goto(url(THAPAR.slug, "/admin/exams"));
  await expect(page.getByText(LIVE)).toBeVisible();
});

test("3 · a marks file with mistakes is caught, nothing is saved; the fixed file imports", async ({
  page,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const midsem = (await examsOf(page)).find((e) => e.name === MIDSEM)!;
  await page.goto(url(THAPAR.slug, `/admin/imports?kind=marks&exam=${midsem.id}`));
  await page.getByLabel("Papers in the file").selectOption({ label: "UCS301 — Data Structures" });
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(FILES, "thapar-midsem-UCS301-with-errors.csv"));
  await expect(page).toHaveURL(/\/admin\/imports\/[\w-]+$/);
  await expect(page.getByText("Ready to review")).toBeVisible({ timeout: 30_000 });
  const report = page.getByRole("table");
  await expect(report.getByText(/Internal: 45 is outside 0–40/)).toBeVisible();
  await expect(report.getByText(/102409999/).first()).toBeVisible(); // a student who isn't in the exam

  await page.getByRole("button", { name: "Upload fixed file" }).click();
  await page
    .getByRole("dialog")
    .locator('input[type="file"]')
    .setInputFiles(path.join(FILES, "thapar-midsem-UCS301-fixed.csv"));
  await expect(page.getByText("Saves marks for 120 students")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Import 120 rows" }).click();
  await page
    .getByRole("dialog", { name: "Save these marks?" })
    .getByRole("button", { name: "Save marks" })
    .click();
  await expect(page.getByRole("heading", { name: "Marks saved" })).toBeVisible({ timeout: 30_000 });
});

test("4 · publish live; the student sees it on a phone, with their SGPA and two years of history", async ({
  page,
  browser,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const live = (await examsOf(page)).find((e) => e.name === LIVE)!;
  await page.goto(url(THAPAR.slug, `/admin/exams/${live.id}/results`));
  await expect(page.getByText(/Approved and ready/)).toBeVisible();
  await page.getByRole("button", { name: "Publish now" }).click();
  await page
    .getByRole("dialog", { name: /Publish to \d+ students now\?/ })
    .getByRole("button", { name: "Publish now" })
    .click();
  await expect(page.getByText(/Live since/)).toBeVisible({ timeout: 15_000 });

  const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await signIn(phone, THAPAR.slug, STUDENT, DEMO_PASSWORD);
  const latest = phone.getByRole("link", { name: /Latest result/ });
  await expect(latest).toContainText(LIVE);
  await expect(latest).toContainText("SGPA");
  const history = phone.getByRole("region", { name: "Earlier results" });
  await expect(history.getByRole("listitem")).toHaveCount(3);
  await expect(history).toContainText(/Academic year 2024.25/); // two academic years of results
  await expect(history).toContainText(/Academic year 2025.26/);
});

test("5 · the official PDF verifies: genuine, current, and the file matches", async ({ page, browser }) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const live = (await examsOf(page)).find((e) => e.name === LIVE)!;
  await page.goto(url(THAPAR.slug, `/admin/exams/${live.id}/results`));
  await expect(page.getByText(/marksheets are ready to download/)).toBeVisible({ timeout: 120_000 });

  const sp = await (await browser.newContext()).newPage();
  await signIn(sp, THAPAR.slug, STUDENT, DEMO_PASSWORD);
  await sp.getByRole("link", { name: /Latest result/ }).click();
  const card = sp.getByRole("region", { name: "Marksheet (PDF)" });
  const [download] = await Promise.all([
    sp.waitForEvent("download"),
    card.getByRole("button", { name: "Download" }).click(),
  ]);
  const pdf = await readFile(await download.path());
  const fingerprint = createHash("sha256").update(pdf).digest("hex");
  const verifier = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await verifier.goto(`http://${await card.locator("code").textContent()}`);
  await expect(verifier.getByRole("heading", { name: "Valid" })).toBeVisible();
  await expect(verifier.getByText(fingerprint)).toBeVisible();
});

test("6 · isolation: Thapar's session means nothing at Demo School", async ({ page }) => {
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const session = (await page.context().cookies(url(THAPAR.slug))).find((c) => c.name.endsWith("sc_session"));
  const res = await page.request.get(`http://127.0.0.1:${PORT}/api/v1/me`, {
    headers: { Host: `demoschool.${BASE}:${PORT}`, Cookie: `sc_session=${session!.value}` },
  });
  expect(res.status()).toBe(401);
});

test("7 · plans: Demo School on Free sees its limits; Demo Coaching's students see ranks", async ({
  page,
  browser,
}) => {
  await signIn(page, DEMO_TENANTS.demoschool.slug, DEMO_TENANTS.demoschool.owner);
  await page.goto(url(DEMO_TENANTS.demoschool.slug, "/admin/plan"));
  const table = page.getByRole("table", { name: "Plans and what they include" });
  await expect(table.getByRole("columnheader", { name: /Free/ })).toContainText("Current");

  const coaching = await (await browser.newContext()).newPage();
  await signIn(coaching, DEMO_TENANTS.democoaching.slug, "DCA251001", DEMO_PASSWORD);
  await coaching.getByRole("link", { name: /Latest result/ }).click();
  await expect(coaching.getByRole("article", { name: /Result of / })).toContainText("Rank");
});

test("8 · the platform console sees every institution and its plan, never their students", async ({
  page,
}) => {
  await page.goto(url("admin", "/login"));
  await page.getByLabel("Work email").fill(DEMO_PLATFORM.email);
  await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByLabel("Authenticator code").fill(totp(DEMO_PLATFORM.totpSecret));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.getByRole("link", { name: "Institutions" }).click();
  for (const t of Object.values(DEMO_TENANTS))
    await expect(page.getByRole("link", { name: t.name })).toBeVisible();
});
