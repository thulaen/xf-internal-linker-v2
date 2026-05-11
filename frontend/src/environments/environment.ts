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
  // OpenTelemetry collector OTLP/HTTP endpoint. Same host:port pattern as
  // the backend collector — runs on `otel-collector:4318` inside the docker
  // network and is also exposed to the host. Browser requests go to the
  // host-port surface. Empty string disables browser tracing.
  otelEndpoint: 'http://localhost:4318',
  // Grafana Faro (added 2026-05-11). Real User Monitoring — JS errors,
  // Web Vitals (LCP/INP/CLS), session events. Ships to the Alloy
  // faro.receiver block on port 12347. Empty URL disables Faro
  // bootstrap. Sits ALONGSIDE OpenTelemetry (no shared tracer).
  faroEnabled: true,
  faroEndpoint: 'http://localhost:12347/collect',
  faroSessionSampleRate: 1.0,
};
