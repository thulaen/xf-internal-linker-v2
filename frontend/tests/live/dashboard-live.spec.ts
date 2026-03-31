import { expect, test } from '@playwright/test';

test('live dashboard loads with the real backend', async ({ page }, testInfo) => {
  test.skip(process.env.PLAYWRIGHT_LIVE !== '1', 'Live backend mode only');

  await page.goto('/dashboard');

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('Recent Pipeline Runs')).toBeVisible();
  await expect(page.getByText('Recent Imports')).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath('dashboard-live.png'),
    fullPage: true,
  });
});
