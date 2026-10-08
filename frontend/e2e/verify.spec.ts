import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_TENANTS, apiAs, approvedQuiz, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;
const STUDENT = "102401001"; // the seeded student with an account, in COE-2A

test("E2E-4: a verifier checks a downloaded marksheet; a withdrawal shows at once", async ({
  page,
  browser,
}) => {
  test.slow();
  await signIn(page, THAPAR.slug, THAPAR.owner);
  const exam = await approvedQuiz(page, "COE-2A", { [STUDENT]: { INT: "31", EXT: "47" } });
  const pubs = `/api/v1/admin/exams/${exam.examId}/publications`;
  const pub = await apiAs<{ id: string }>(page, "POST", pubs, {}, { "Idempotency-Key": crypto.randomUUID() });

  // The worker prepares every marksheet right after publication; the administrator watches it finish.
  await page.goto(url(THAPAR.slug, `/admin/exams/${exam.examId}/results`));
  await expect(page.getByText(/marksheets are ready to download/)).toBeVisible({ timeout: 90_000 });

  // The student downloads the official PDF.
  const student = await browser.newContext();
  const sp = await student.newPage();
  await signIn(sp, THAPAR.slug, STUDENT, DEMO_PASSWORD);
  await sp.goto(url(THAPAR.slug, `/me/results/${pub.id}`));
  const card = sp.getByRole("region", { name: "Marksheet (PDF)" });
  const [download] = await Promise.all([
    sp.waitForEvent("download"),
    card.getByRole("button", { name: "Download" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^Marksheet-102401001-Quiz-.+\.pdf$/);
  const pdf = await readFile(await download.path());
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  const fingerprint = createHash("sha256").update(pdf).digest("hex");
  const verifyUrl = `http://${await card.locator("code").textContent()}`;
  await student.close();

  // Anyone (no account, on a phone) checks it: genuine, current, and the file matches what was issued.
  const verifier = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const vp = await verifier.newPage();
  const response = await vp.goto(verifyUrl);
  expect(response?.headers()["x-robots-tag"]).toContain("noindex");
  await expect(vp.getByRole("heading", { name: "Valid" })).toBeVisible();
  await expect(vp.getByText(fingerprint)).toBeVisible();
  await expect(vp.locator("main")).not.toContainText(STUDENT); // identity is masked
  await expect(vp.locator("main")).not.toContainText("78 / 100"); // and marks are never shown
  const a11y = await new AxeBuilder({ page: vp }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(a11y.violations).toEqual([]);

  // Withdrawn results say so to the next person who checks.
  await apiAs(page, "POST", `${pubs}/${pub.id}/withdraw`, { reason: "E2E: verification follows withdrawal" });
  await vp.reload();
  await expect(vp.getByRole("heading", { name: "Withdrawn" })).toBeVisible();

  // A mistyped code gets a helpful answer, not an error page.
  await vp.goto(url("verify", "/v"));
  await vp.getByLabel("Verification code").fill("hello");
  await vp.getByRole("button", { name: "Verify" }).click();
  await expect(vp.getByText(/isn't a verification code/)).toBeVisible();
  await verifier.close();
});
