import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:4200';
const useExistingApp = process.env.PLAYWRIGHT_NO_WEBSERVER === '1';
// When PLAYWRIGHT_CI=1 the runner skips:
//   - `tests/live/**` (need a real backend stack with seeded data — CI has no backend)
//   - `tests/capture/**` (manual screenshot tool, not a behavioural test)
// Local runs still include everything. New live specs and capture specs
// are auto-excluded from CI; new top-level smoke specs are auto-included.
const isCIRun = process.env.PLAYWRIGHT_CI === '1';

export default defineConfig({
  testDir: './tests',
  testIgnore: isCIRun ? ['**/live/**', '**/capture/**'] : [],
  fullyParallel: true,
  retries: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: useExistingApp
    ? undefined
    : {
        command: 'npm start',
        url: baseURL,
        reuseExistingServer: true,
        timeout: 120000,
      },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          // Prevent Chromium from offering to save or update passwords during
          // test runs. Without these flags the browser can write to the OS
          // keychain or to a shared Chrome profile, which corrupts the saved
          // password for localhost in the user's real browser.
          args: [
            '--disable-features=PasswordImport',
            '--disable-password-manager-reauthentication',
            '--password-store=basic',
          ],
        },
      },
    },
  ],
});
