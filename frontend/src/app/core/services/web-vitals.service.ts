import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from 'web-vitals';

/**
 * Phase E2 / Gap 51 — Core Web Vitals telemetry.
 *
 * Subscribes to the four "Core" vitals that Google uses to rank user
 * experience — LCP, CLS, INP — plus FCP and TTFB for diagnostic context.
 * Each metric fires once per page-load when the underlying observer is
 * confident the number has settled. We POST the result to the backend
 * telemetry endpoint; the Performance page charts them later (Gap 130).
 *
 * The four thresholds we care about (Google, as of 2025):
 *   LCP  ≤ 2.5s = good; ≤ 4.0s = needs-improvement
 *   INP  ≤ 200ms = good; ≤ 500ms = needs-improvement
 *   CLS  ≤ 0.1 = good;  ≤ 0.25 = needs-improvement
 *
 * `web-vitals` computes `rating: 'good' | 'needs-improvement' | 'poor'`
 * for us — we forward it to the backend verbatim so the dashboard can
 * colour-code without re-deriving thresholds.
 *
 * Design:
 *   - Fire-and-forget POST. No retry, no queueing. If the beacon drops,
 *     we lose one data point — not worth a complex buffer.
 *   - `navigator.sendBeacon` preferred over `fetch` because the browser
 *     guarantees delivery even during page-unload (common for CLS,
 *     which finalizes on navigation away). We fall back to `HttpClient`
 *     for dev tooling convenience when `sendBeacon` is unavailable.
 *   - No PII — we send metric name, value, rating, navigation type,
 *     and current pathname (NOT query string). No user IDs.
 */
@Injectable({ providedIn: 'root' })
export class WebVitalsService {
  private readonly http = inject(HttpClient);
  private started = false;
  private readonly endpoint = '/api/telemetry/web-vitals/';

  /** Wire up once from AppComponent ngOnInit. Safe to call repeatedly. */
  start(): void {
    if (this.started) return;
    this.started = true;

    const report = (metric: Metric): void => this.report(metric);

    // `reportAllChanges: false` = one final value per metric per page.
    // For INP we explicitly want all changes (since INP is the WORST
    // interaction delay over the page lifetime, it monotonically grows
    // — the backend dedupes by (sessionId, metricName) + keeps max).
    onLCP(report);
    onCLS(report);
    onINP(report, { reportAllChanges: true });
    onFCP(report);
    onTTFB(report);
  }

  private report(metric: Metric): void {
    const payload = {
      name: metric.name,
      value: metric.value,
      rating: metric.rating,
      delta: metric.delta,
      id: metric.id,
      navigation_type: metric.navigationType,
      path: location.pathname,
      // Best-effort: the user-agent hint API lets us attribute numbers
      // to device tiers without shipping a raw UA string.
      device_memory: (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? null,
      effective_connection_type:
        (navigator as Navigator & { connection?: { effectiveType?: string } }).connection?.effectiveType ?? null,
      timestamp: Date.now(),
    };

    // Prefer sendBeacon — the browser guarantees delivery even if the
    // user closes the tab between metric emit and network ack.
    if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      try {
        const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
        const ok = navigator.sendBeacon(this.endpoint, blob);
        if (ok) return;
      } catch {
        // Fall through to HttpClient below.
      }
    }

    // Fallback for environments without sendBeacon (or a failed beacon
    // — e.g. the user's browser is in a quirky state). Errors are
    // swallowed because telemetry is best-effort.
    this.http.post(this.endpoint, payload).subscribe({
      error: () => {
        /* best-effort — drop silently */
      },
    });
  }
}
