import { expect, test } from '@playwright/test';
import { mockDashboardApis } from './support/mock-api';

test('dashboard loads in a real browser and saves a screenshot', async ({ page }, testInfo) => {
  await mockDashboardApis(page);

  await page.goto('/dashboard');

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('Pending review')).toBeVisible();
  await expect(page.getByText('Recent Pipeline Runs')).toBeVisible();
  await expect(page.getByText('Recent Imports')).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath('dashboard.png'),
    fullPage: true,
  });
});
