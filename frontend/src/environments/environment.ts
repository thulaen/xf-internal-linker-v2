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
  // Phase GT Step 2 — Sentry/GlitchTip DSN. Leave blank in dev to skip
  // initialisation entirely. Paste the DSN from GlitchTip (or paid Sentry)
  // to start capturing JS errors.
  glitchtipDsn: '',
};
