/**
 * Angular 20 application entry point.
 * Uses the standalone component API (no NgModules).
 *
 * Phase GT Step 2 — Sentry/GlitchTip SDK is initialised here, BEFORE
 * bootstrapApplication, so that any error thrown during bootstrap is
 * captured. When `environment.glitchtipDsn` is empty (the default in
 * dev), `Sentry.init` is never called — zero overhead, zero network.
 */

// `@angular/localize/init` MUST be imported before any component class is
// instantiated. It sets up the global `$localize` template tag so any
// `i18n=` attribute or `$localize`-tagged template literal works at
// runtime. With this import in place, English (en-US) is the source
// locale; additional locales are added by extracting and translating
// `messages.xlf` then building per-locale bundles via `ng build --localize`.
import '@angular/localize/init';
import { bootstrapApplication } from '@angular/platform-browser';
import * as Sentry from '@sentry/angular';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';
import { initFaroBrowser } from './app/core/observability/faro-bootstrap';
import { initOtelBrowser } from './app/core/observability/otel-bootstrap';
import { environment } from './environments/environment';

// Browser-side OpenTelemetry — every fetch / XHR / page-load becomes a
// span exported to the same OTel collector the backend uses. Sentry
// already handles errors + Web Vitals; OTEL handles the trace tree so
// browser → backend → DB → C++ shows up as one trace in GlitchTip's
// Performance tab. Empty endpoint disables.
//
// Skip when running under Karma — the ZoneContextManager that
// `initOtelBrowser` installs as the global context manager conflicts
// with Angular TestBed's own zone, causing tab labels to never render
// and the suite to time out / disconnect. Karma sets `__karma__` on
// window before any test bootstrap, so this gate is reliable.
const inKarma = typeof window !== 'undefined' && '__karma__' in window;
if (environment.otelEndpoint && !inKarma) {
  initOtelBrowser({
    endpoint: environment.otelEndpoint,
    serviceName: 'xf-linker-frontend',
    serviceVersion: environment.appVersion,
    environment: environment.production ? 'production' : 'development',
  });
}

// Grafana Faro — Real User Monitoring (added 2026-05-11). Faro covers
// JS errors, Web Vitals (LCP/INP/CLS) and session events. Ships to the
// Alloy faro.receiver and from there into Loki, where `faro_picker`
// promotes recurring problems into AutoIssue rows. Sits alongside the
// OTel browser tracer — both SDKs run independently, no shared state.
// Skipped under Karma so test runs don't try to reach the receiver.
if (environment.faroEnabled && environment.faroEndpoint && !inKarma) {
  initFaroBrowser({
    url: environment.faroEndpoint,
    appName: 'xf-linker-frontend',
    appVersion: environment.appVersion,
    environment: environment.production ? 'production' : 'development',
    sessionSampleRate: environment.faroSessionSampleRate,
  });
}

if (environment.glitchtipDsn) {
  Sentry.init({
    dsn: environment.glitchtipDsn,
    environment: environment.production ? 'production' : 'development',
    release: environment.appVersion,
    // Browser-side traces — 100% sampling in dev so EVERY navigation
    // surfaces LCP/FID/CLS measurements + the trace tree in GlitchTip's
    // Performance tab. Cost: ~3.3× more events at single-host dev scale,
    // still tens of MB/week. For any prod-style deployment, override via
    // a build-time replacement of `environment.ts` to a smaller rate.
    tracesSampleRate: 1.0,
    // Session Replay (added 2026-05-09): records DOM mutations + console
    // around every captured error. Lets us see what the user clicked /
    // typed / scrolled before a JS crash. Cost: ~50 KB lazy-loaded SDK
    // plus per-replay storage in the GlitchTip events DB. The 0.0 idle
    // sample rate plus 1.0 on-error sample rate means we only record when
    // an error fires — no recording on healthy sessions.
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 1.0,
    integrations: [
      Sentry.replayIntegration({
        // Mask all text input + media to avoid leaking PII into the replay.
        maskAllText: true,
        blockAllMedia: true,
      }),
      // Web Vitals — captures Largest Contentful Paint, Interaction-to-
      // Next-Paint, Cumulative Layout Shift, First Input Delay, Time to
      // First Byte. These are rendered as measurements on the
      // page-load transaction in GlitchTip's Performance tab. Closes a
      // gap neither GlitchTip-error-only nor Pyroscope catches: "the
      // app feels slow but nothing crashed and no Python is hot".
      Sentry.browserTracingIntegration({
        // Auto-capture every navigation as a transaction; default tracePropagationTargets is fine.
      }),
    ],
    // Don't send PII — the backend is the source of truth for user data
    // and our error reports don't need to duplicate it.
    sendDefaultPii: false,
    // Stack the frontend release tag with a node-style origin hint so a
    // single GlitchTip project can host multiple environments cleanly.
    initialScope: {
      tags: {
        node_role: 'frontend',
      },
    },
  });
}

bootstrapApplication(AppComponent, appConfig).catch((err) =>
  console.error(err)
);
