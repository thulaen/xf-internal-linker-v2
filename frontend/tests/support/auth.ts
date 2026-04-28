import { Page } from '@playwright/test';

/**
 * Seeds an auth token in localStorage so the Angular auth guard lets the
 * test through without a real /api/auth/token/ round-trip. Pair with
 * `mockDashboardApis(page)` so /api/auth/me/ also returns a usable user.
 *
 * Requires a prior page.goto() to a same-origin URL — localStorage is
 * per-origin and is not accessible at about:blank. We navigate to /login
 * first because that page never requires auth.
 */
export async function loginAsTestUser(page: Page): Promise<void> {
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.setItem('xfil_auth_token', 'ci-test-token');
    localStorage.setItem('xfil_auth_token_issued_at', String(Date.now()));
  });
}
