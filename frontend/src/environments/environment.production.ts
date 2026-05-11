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
  glitchtipBaseUrl: `${window.location.protocol}//${window.location.hostname}:1337`,
  // Phase GT Step 2 — Sentry/GlitchTip DSN. The DSN is a public client
  // identifier (NOT a secret) — Sentry intentionally embeds it in client-
  // side JS. For this dev/local stack the DSN points at the host port
  // (`localhost:1337`) because the browser runs on the host. For prod
  // deploys, replace this string at build time with the production DSN.
  glitchtipDsn: 'http://2887afdd98bb447ba734ab8d653fee27@localhost:1337/1',
  // OpenTelemetry collector OTLP/HTTP endpoint. The browser runs on the
  // host so we point at the host-exposed port (`:4318`). Empty disables
  // browser tracing.
  otelEndpoint: `${window.location.protocol}//${window.location.hostname}:4318`,
  // Grafana Faro (added 2026-05-11). Real User Monitoring — JS errors,
  // Web Vitals (LCP/INP/CLS), session events. Ships to the Alloy
  // faro.receiver block on the host-exposed port. Sits ALONGSIDE
  // OpenTelemetry; no shared tracer. Session sampling drops to 25 %
  // in production so a busy site doesn't flood Loki.
  faroEnabled: true,
  faroEndpoint: `${window.location.protocol}//${window.location.hostname}:12347/collect`,
  faroSessionSampleRate: 0.25,
};
