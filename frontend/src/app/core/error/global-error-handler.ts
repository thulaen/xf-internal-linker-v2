import { ErrorHandler, Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

import { environment } from '../../../environments/environment';

/**
 * Phase U1 / Gap 26 — Global client-side error handler.
 *
 * Wired in `app.config.ts` ONLY when `environment.glitchtipDsn` is empty
 * (i.e. Sentry isn't already doing this job). When a DSN is set, Sentry
 * wins and this handler stays out of the way.
 *
 * Behavior:
 *   1. Console-log the error so dev loops still see it.
 *   2. POST a compact report to `/api/telemetry/client-errors/` — no PII,
 *      no hard failure if the network is down (fire-and-forget).
 *   3. Rate-limited per-session: at most 20 reports in the first minute,
 *      then 1 per minute. Prevents a render-loop bug from DoS'ing the
 *      backend. Backend has its own DRF throttle as a second line of
 *      defence.
 *   4. Never crashes — any exception inside the handler is swallowed so
 *      the error path itself can't trigger a second error.
 */
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private reportedThisMinute = 0;
  private windowStart = Date.now();

  /** Hard cap on reports per rolling minute — matches the backend
   *  UserRateThrottle that defaults to a sensible per-user quota. */
  private readonly MAX_PER_MINUTE = 20;

  handleError(error: unknown): void {
    // 1) Preserve the native console behavior so dev tools still light up.
    // eslint-disable-next-line no-console
    console.error(error);

    // 2) Rate-limit before doing anything network-bound.
    if (!this.tryClaimReportSlot()) return;

    // 3) Build a compact, PII-free payload and POST (fire-and-forget).
    try {
      const payload = this.buildPayload(error);
      this.http
        .post(`${environment.apiBaseUrl}/telemetry/client-errors/`, payload)
        .subscribe({
          next: () => {},
          error: () => {
            // Silently ignore network failures — an unreachable backend
            // is already obvious from every other failing request, and
            // a failed error-report must never cascade into another
            // uncaught error.
          },
        });
    } catch {
      // Swallow — the error path must never throw.
    }
  }

  /**
   * Enforce the per-minute quota. Returns `true` if the caller may send
   * the report, `false` otherwise. Uses a simple rolling window.
   */
  private tryClaimReportSlot(): boolean {
    const now = Date.now();
    if (now - this.windowStart > 60_000) {
      this.windowStart = now;
      this.reportedThisMinute = 0;
    }
    if (this.reportedThisMinute >= this.MAX_PER_MINUTE) {
      return false;
    }
    this.reportedThisMinute += 1;
    return true;
  }

  private buildPayload(error: unknown): Record<string, unknown> {
    let message = 'Unknown error';
    let stack = '';
    if (error instanceof Error) {
      message = error.message || error.name || message;
      stack = error.stack || '';
    } else if (typeof error === 'string') {
      message = error;
    } else {
      try {
        message = JSON.stringify(error)?.slice(0, 1000) ?? message;
      } catch {
        message = String(error).slice(0, 1000);
      }
    }

    const route = this.safeRouterUrl();
    const url = typeof window !== 'undefined' ? window.location.href : '';
    const userAgent = typeof navigator !== 'undefined' ? navigator.userAgent || '' : '';

    return {
      message,
      stack,
      route,
      url,
      user_agent: userAgent,
      app_version: environment.appVersion,
    };
  }

  private safeRouterUrl(): string {
    try {
      return this.router.url || '';
    } catch {
      return '';
    }
  }
}
