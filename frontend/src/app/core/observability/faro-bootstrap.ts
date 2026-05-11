/**
 * Browser-side Grafana Faro bootstrap.
 *
 * Faro covers Real User Monitoring — JS errors, Web Vitals
 * (LCP/INP/CLS), session events, page-load timings. It sits ALONGSIDE
 * the existing OpenTelemetry browser tracer (`otel-bootstrap.ts`),
 * which keeps owning span propagation through GlitchTip's Sentry
 * exporter. Both SDKs are independent; they share no state.
 *
 * Events ship over HTTP to the Alloy `faro.receiver` block in
 * `config.alloy`, which forwards them to Loki with the label set
 * `{service="frontend", source="faro"}`. The backend `faro_picker`
 * (apps.auto_issues.services.faro_picker) reads those streams via
 * LogQL and promotes recurring problems to AutoIssue rows.
 *
 * Added 2026-05-11 per plan
 * ~/.claude/plans/objective-deploy-and-integrate-zany-bee.md Stream 3.
 */
import {
  getWebInstrumentations,
  initializeFaro,
  LogLevel,
} from '@grafana/faro-web-sdk';

export interface FaroBootstrapOptions {
  /** HTTP collect URL on the Alloy faro.receiver. Empty disables. */
  url: string;
  /** Service name attached to every event ("xf-linker-frontend"). */
  appName?: string;
  /** App version (matches Angular package version). */
  appVersion?: string;
  /** Environment tag ("production" | "development"). */
  environment?: string;
  /** Fraction of sessions to record (0.0–1.0). Default 1.0. */
  sessionSampleRate?: number;
}

let _initialized = false;

/**
 * Initialise the Faro Web SDK. Idempotent — safe to call twice; the
 * second call is a no-op so HMR doesn't double-register.
 *
 * Defensive: every step is wrapped in try/catch so a missing dep or
 * blocked endpoint never breaks app bootstrap. Errors land in
 * `console.warn` so they're debuggable without a hard crash.
 */
export function initFaroBrowser(options: FaroBootstrapOptions): void {
  if (_initialized) return;
  if (!options.url) return;

  try {
    initializeFaro({
      url: options.url,
      app: {
        name: options.appName ?? 'xf-linker-frontend',
        version: options.appVersion ?? 'dev',
        environment: options.environment ?? 'development',
      },
      instrumentations: [
        // captureConsole=true forwards console.error / console.warn
        // into Faro so the picker sees devtools-only errors too.
        ...getWebInstrumentations({
          captureConsole: true,
          // LogLevel is a TS enum; passing the enum members keeps strict
          // type-check happy. We suppress debug/info/log so only warn +
          // error reach Loki — those are the levels the faro_picker
          // promotes to AutoIssue, and the others are noise.
          captureConsoleDisabledLevels: [
            LogLevel.DEBUG,
            LogLevel.INFO,
            LogLevel.LOG,
          ],
        }),
      ],
      sessionTracking: {
        enabled: true,
        samplingRate: options.sessionSampleRate ?? 1.0,
      },
      // Pause the SDK if the receiver is unreachable so we don't queue
      // unbounded events in memory.
      isolate: true,
      // Don't send default trace context — OTel browser tracer owns that.
      trackResources: false,
      trackWebVitalsAttribution: true,
    });

    _initialized = true;
  } catch (err) {
    console.warn('[faro-browser] init failed', err);
  }
}

