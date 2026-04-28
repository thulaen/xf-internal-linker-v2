import { expect, test } from '@playwright/test';
import { mockDashboardApis } from './support/mock-api';
import { loginAsTestUser } from './support/auth';

test('dashboard loads in a real browser and saves a screenshot', async ({ page }, testInfo) => {
  await mockDashboardApis(page);
  await loginAsTestUser(page);

  await page.goto('/dashboard');
  // Wait for the dashboard data to bind — the stat cards are gated on `data()`
  // being populated by the mocked /api/dashboard/ response.
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  // exact: true — there's also a "Pending reviews" (plural) chart label.
  await expect(page.getByText('Pending review', { exact: true })).toBeVisible();
  await expect(page.getByText('Recent Pipeline Runs')).toBeVisible();
  await expect(page.getByText('Recent Imports')).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath('dashboard.png'),
    fullPage: true,
  });
});
