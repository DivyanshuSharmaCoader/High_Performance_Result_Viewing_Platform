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
    // The browser's own controls (date fields) follow its language, not the page locale: dd/mm/yyyy.
    launchOptions: { args: ["--lang=en-IN"] },
    timezoneId: "Asia/Kolkata",
    actionTimeout: 20_000, // a missing element fails in seconds, not at the 15-minute test timeout
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
