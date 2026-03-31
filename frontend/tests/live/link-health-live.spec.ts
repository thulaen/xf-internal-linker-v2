import { expect, test } from '@playwright/test';

test('live link health page loads with the real backend', async ({ page }) => {
  test.skip(process.env.PLAYWRIGHT_LIVE !== '1', 'Live backend mode only');

  await page.goto('/link-health');

  await expect(page.getByRole('heading', { name: 'Link Health' })).toBeVisible();
  await expect(page.locator('.summary-card.summary-open .summary-label')).toBeVisible();
});
