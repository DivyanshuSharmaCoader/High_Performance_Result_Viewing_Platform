import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the full container stack (`make stack && make seed-stack`) on
 * http://*.localhost:8080. Hosts differ per test (host-based tenancy), so tests use absolute URLs.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // Two workers: on a laptop the browsers and the Docker VM compete for CPU (see
  // benchmarks/results/2026-10-06-dev-environment-latency.md).
  workers: 2,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
});
