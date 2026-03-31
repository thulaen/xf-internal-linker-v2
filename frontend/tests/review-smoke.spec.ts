import { expect, test } from '@playwright/test';
import { mockDashboardApis } from './support/mock-api';

test('review page loads suggestion cards in a real browser', async ({ page }) => {
  await mockDashboardApis(page);

  await page.goto('/review');

  await expect(page.getByRole('heading', { name: 'Review' })).toBeVisible();
  await expect(page.locator('.destination-title', { hasText: 'Internal Linking Guide' })).toBeVisible();
  await expect(page.locator('.card-host', { hasText: 'Anchor Text Best Practices' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve', exact: true })).toBeVisible();
});
