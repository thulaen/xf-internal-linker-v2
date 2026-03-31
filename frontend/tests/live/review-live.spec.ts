import { expect, test } from '@playwright/test';

test('live review page loads with the real backend', async ({ page }) => {
  test.skip(process.env.PLAYWRIGHT_LIVE !== '1', 'Live backend mode only');

  await page.goto('/review');

  await expect(page.getByRole('heading', { name: 'Review' })).toBeVisible();
  await expect(page.getByText('Suggestion workspace')).toBeVisible();
});
