import { expect, test } from '@playwright/test';
import { mockDashboardApis } from '../support/mock-api';
import { loginAsTestUser } from '../support/auth';

function readSetting(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}

test('capture a named UI snapshot', async ({ page }, testInfo) => {
  const route = readSetting('PLAYWRIGHT_CAPTURE_ROUTE', '/dashboard');
  const name = readSetting('PLAYWRIGHT_CAPTURE_NAME', 'page-snapshot');

  // In CI we have no backend — mock the API and seed an auth token.
  // Local "ui:snap:live" runs (which set PLAYWRIGHT_NO_WEBSERVER=1) skip
  // both so the snapshot reflects real data from the running prod stack.
  if (process.env.PLAYWRIGHT_CI === '1') {
    await mockDashboardApis(page);
    await loginAsTestUser(page);
  }

  await page.goto(route);
  await expect(page.locator('body')).toBeVisible();
  await page.waitForLoadState('networkidle').catch(() => {});

  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
});
