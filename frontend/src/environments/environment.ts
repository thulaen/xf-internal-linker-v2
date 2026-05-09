/**
 * Development environment configuration.
 * API calls proxy to Django backend via proxy.conf.json.
 */

export const environment = {
  production: false,
  apiBaseUrl: '/api',
  adminUrl: 'http://localhost:8000/admin/',
  wsBaseUrl: 'ws://localhost:8000/ws',
  appVersion: '2.0.0',
  glitchtipBaseUrl: 'http://localhost:1337',
  // Phase GT Step 2 — Sentry/GlitchTip DSN. The DSN is a public client
  // identifier (NOT a secret) — Sentry intentionally embeds it in client-
  // side JS. Browser-side DSN points at the host port (`localhost:1337`)
  // because the browser runs on the host. The backend uses a different
  // DSN that points at `glitchtip:8000` (in-network hostname) — see `.env`.
  glitchtipDsn: 'http://2887afdd98bb447ba734ab8d653fee27@localhost:1337/1',
};
