import { expect, test } from "@playwright/test";

import { latestEmail, linkFrom, uniq, url } from "./support";

test("E2E-1: sign up → verify email → land in the new portal's onboarding checklist", async ({ page }) => {
  const name = `E2E Academy ${uniq("")}`;
  const email = `${uniq("owner")}@e2e.example.com`;
  await page.goto(url("", "/signup"));
  await page.getByLabel("Institution name").fill(name);
  const slug = await page.getByLabel("Portal address").inputValue();
  expect(slug).toMatch(/^e2e-academy-/);
  await expect(page.getByText("Available")).toBeVisible();
  await page.getByLabel("Type").selectOption("coaching");
  await page.getByLabel("Your name").fill("E2E Owner");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("an-e2e-owner-passphrase");
  await page.getByRole("button", { name: "Create portal" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  const mail = await latestEmail(email);
  await page.goto(linkFrom(mail.text, /http:\/\/\S+\/signup\/verify\?token=[\w-]+/));
  await expect(page).toHaveURL(url(slug, "/admin"), { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Set up your institution" })).toBeVisible();
  await expect(page.getByText("0 of 3 steps done")).toBeVisible();
  await expect(page.getByText(name).first()).toBeVisible();
});

test("@mobile the sign-in page works on a phone", async ({ page }) => {
  await page.goto(url("thapar", "/login"));
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
