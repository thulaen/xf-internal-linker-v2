/**
 * Production environment configuration.
 * API calls go to the same origin (served by Nginx, proxied to Django).
 */

export const environment = {
  production: true,
  apiBaseUrl: '/api',
  adminUrl: `${window.location.origin}/admin/`,
  wsBaseUrl: `wss://${window.location.host}/ws`,
  appVersion: '2.0.0',
  // Phase GT Step 2 — Sentry/GlitchTip DSN. Set via build-time substitution
  // or runtime config so prod builds don't need source edits. An empty
  // string disables the SDK entirely (no init, no global ErrorHandler
  // hook). For nginx-proxied deploys, a common pattern is to leave this
  // as a placeholder and replace it in Docker entrypoint.
  glitchtipDsn: '',
};
