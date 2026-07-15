import {defineConfig} from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    channel: "chrome",
    viewport: {width: 1440, height: 1000},
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
