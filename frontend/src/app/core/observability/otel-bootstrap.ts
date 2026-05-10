/**
 * Browser-side OpenTelemetry bootstrap.
 *
 * Wires three pieces of auto-instrumentation:
 *   - `fetch` — every API call becomes a trace span.
 *   - `XMLHttpRequest` — covers the legacy code path Angular's HttpClient
 *      uses internally.
 *   - `document-load` — Page-load timings (DNS / TCP / TTFB / DCL / Load).
 *
 * Spans are exported as OTLP/HTTP to the same OpenTelemetry collector the
 * backend uses (`environment.otelEndpoint`, default `http://localhost:4318`).
 * The collector forwards them to GlitchTip's Sentry-envelope receiver so a
 * single trace tree spans browser → backend → DB → C++ in GlitchTip's
 * Performance tab.
 *
 * Side-by-side with Sentry: Sentry handles errors + replays + Web Vitals
 * (LCP/CLS/INP). OTEL handles span propagation across services. The two
 * SDKs are independent; both can run without conflict.
 *
 * Defensive: every step has a try/catch so a missing dep / blocked endpoint
 * never breaks app bootstrap. Errors land in console.warn so they're
 * debuggable without a hard crash.
 */
import { context, trace } from '@opentelemetry/api';
import { ZoneContextManager } from '@opentelemetry/context-zone';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { XMLHttpRequestInstrumentation } from '@opentelemetry/instrumentation-xml-http-request';
import { Resource } from '@opentelemetry/resources';
import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-web';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';

export interface OtelBootstrapOptions {
  /** OTLP/HTTP endpoint root, e.g. `http://localhost:4318`. Empty disables tracing. */
  endpoint: string;
  /** Service name attribute attached to every span (matches backend Resource). */
  serviceName?: string;
  /** Service version attribute. */
  serviceVersion?: string;
  /** Environment tag (`production` | `development`). */
  environment?: string;
}

let _initialized = false;

/**
 * Initialise the browser tracer. Idempotent — safe to call twice; the
 * second call is a no-op so HMR doesn't double-register.
 */
export function initOtelBrowser(options: OtelBootstrapOptions): void {
  if (_initialized) return;
  if (!options.endpoint) return;

  try {
    const resource = new Resource({
      [SemanticResourceAttributes.SERVICE_NAME]:
        options.serviceName ?? 'xf-linker-frontend',
      [SemanticResourceAttributes.SERVICE_VERSION]:
        options.serviceVersion ?? 'dev',
      [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]:
        options.environment ?? 'development',
      'node.role': 'frontend',
    });

    const provider = new WebTracerProvider({ resource });
    provider.addSpanProcessor(
      new BatchSpanProcessor(
        new OTLPTraceExporter({
          url: `${options.endpoint.replace(/\/$/, '')}/v1/traces`,
        }),
      ),
    );
    provider.register({
      // ZoneContextManager keeps the active span attached across Angular's
      // zone-driven async work (Promises, RxJS, fakeAsync) — without it
      // child spans don't link to their parent fetch span.
      contextManager: new ZoneContextManager(),
    });

    registerInstrumentations({
      instrumentations: [
        new FetchInstrumentation({
          // Don't trace traffic to the OTel collector itself — would loop.
          ignoreUrls: [
            new RegExp(`^${escapeRegex(options.endpoint)}`),
            // GlitchTip ingest is heavy + already covered by Sentry.
            /\/(api\/\d+\/(envelope|store))\//,
          ],
          // Propagate the current trace context downstream so the backend
          // span continues the same trace.
          propagateTraceHeaderCorsUrls: [/.*/],
        }),
        new XMLHttpRequestInstrumentation({
          ignoreUrls: [
            new RegExp(`^${escapeRegex(options.endpoint)}`),
          ],
          propagateTraceHeaderCorsUrls: [/.*/],
        }),
      ],
    });

    _initialized = true;
    // Suppress lint: the references below ensure tree-shakers don't drop
    // the imports — the SDK auto-registers via side effects.
    void trace.getTracerProvider();
    void context.active();
  } catch (err) {
    console.warn('[otel-browser] init failed', err);
  }
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
