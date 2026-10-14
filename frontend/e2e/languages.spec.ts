import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_TENANTS, signIn, url } from "./support";

const THAPAR = DEMO_TENANTS.thapar;
const STUDENT = "102401001";

test("P18.4: a student reads the portal in Punjabi or Hindi, and the choice stays on the device", async ({
  browser,
}) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const phone = await context.newPage();
  await signIn(phone, THAPAR.slug, STUDENT, DEMO_PASSWORD);
  await expect(phone).toHaveURL(url(THAPAR.slug, "/me"));
  await expect(phone.getByRole("heading", { level: 1 })).toContainText("Hello");

  await phone.getByRole("combobox", { name: "Language" }).selectOption("pa");
  await expect(phone.getByRole("heading", { level: 1 })).toContainText("ਜੀ ਆਇਆਂ ਨੂੰ");
  await expect(phone.locator("html")).toHaveAttribute("lang", "pa");

  await phone.reload();
  await expect(phone.getByRole("heading", { level: 1 })).toContainText("ਜੀ ਆਇਆਂ ਨੂੰ");
  await phone.getByRole("combobox", { name: "ਭਾਸ਼ਾ" }).selectOption("hi");
  await expect(phone.getByRole("heading", { level: 1 })).toContainText("नमस्ते");
  await expect(phone.getByText("नामांकन संख्या")).toBeVisible();
  await context.close();
});
