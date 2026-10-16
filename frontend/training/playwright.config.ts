import { defineConfig } from "@playwright/test";

/**
 * Training-video recordings (docs/training/README.md): the real application on the container stack
 * (`docker compose --profile app up`), one video per module, in order (each module builds on the last).
 * Not part of the test suite; the training workflow runs it.
 */
export default defineConfig({
  testDir: "./specs",
  timeout: 15 * 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../test-results/training-artifacts",
  use: {
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
