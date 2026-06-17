import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:3000";
const shouldStartWebServer = process.env.PLAYWRIGHT_START_SERVER === "1" || Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 5"], viewport: { width: 375, height: 812 } },
    },
  ],
  webServer: shouldStartWebServer
    ? {
        command: "npm run dev",
        url: baseURL,
        reuseExistingServer: false,
        timeout: 120_000,
      }
    : undefined,
});
