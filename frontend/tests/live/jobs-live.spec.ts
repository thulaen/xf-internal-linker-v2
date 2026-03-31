import { expect, test } from '@playwright/test';

test('live jobs page loads with the real backend', async ({ page }) => {
  test.skip(process.env.PLAYWRIGHT_LIVE !== '1', 'Live backend mode only');

  await page.goto('/jobs');

  await expect(page.getByRole('heading', { name: 'Jobs' })).toBeVisible();
  await expect(page.getByText('Import Content')).toBeVisible();
  await expect(page.getByText('Recent Activity')).toBeVisible();
});
