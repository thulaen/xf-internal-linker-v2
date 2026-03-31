import { expect, test } from '@playwright/test';

test('live settings page loads without TypeErrors', async ({ page }) => {
  test.skip(process.env.PLAYWRIGHT_LIVE !== '1', 'Live backend mode only');

  const consoleTypeErrors: string[] = [];

  page.on('console', (message) => {
    if (message.type() !== 'error') {
      return;
    }

    const text = message.text();
    if (text.includes('TypeError')) {
      consoleTypeErrors.push(text);
    }
  });

  await page.goto('/settings');

  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save phrase matching settings' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save March 2026 PageRank settings' })).toBeVisible();
  await expect(page.getByText('Recommended', { exact: false })).toBeVisible();

  expect(consoleTypeErrors).toEqual([]);
});
