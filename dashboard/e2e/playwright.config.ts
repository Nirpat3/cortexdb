import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for CortexDB Dashboard E2E tests.
 *
 * By default, tests run against http://localhost:3400 (the Next.js dev port).
 * Set DASHBOARD_URL to override.
 */
export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: '../playwright-report' }],
    ['list'],
  ],
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },

  use: {
    baseURL: process.env.DASHBOARD_URL || 'http://localhost:3400',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
  ],

  /* Start the dashboard dev server before running tests (optional).
     Uncomment if you want Playwright to manage the server lifecycle. */
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:3400',
  //   reuseExistingServer: !process.env.CI,
  //   timeout: 60_000,
  // },
});
