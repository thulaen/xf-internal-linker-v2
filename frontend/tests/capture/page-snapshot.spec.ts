import { expect, test } from '@playwright/test';

function readSetting(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}

test('capture a named UI snapshot', async ({ page }, testInfo) => {
  const route = readSetting('PLAYWRIGHT_CAPTURE_ROUTE', '/dashboard');
  const name = readSetting('PLAYWRIGHT_CAPTURE_NAME', 'page-snapshot');

  await page.goto(route);
  await expect(page.locator('body')).toBeVisible();
  await page.waitForLoadState('networkidle').catch(() => {});

  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
});
