/**
 * Error interceptor — catches HTTP errors and shows friendly notifications.
 * 401/403 are handled by the auth interceptor, so we skip them here
 * to avoid duplicate toasts and conflicting navigation.
 *
 * Enterprise-grade features:
 * - Single retry on 5xx errors (covers transient blips)
 * - 429 rate-limit handling with Retry-After countdown (Gap 43)
 * - Network error cause distinction
 */

import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { MatSnackBar, MatSnackBarRef } from '@angular/material/snack-bar';
import { catchError, retry, throwError, timer } from 'rxjs';

import {
  RateLimitSnackbarComponent,
  RateLimitSnackbarData,
} from './rate-limit-snackbar.component';

/**
 * Singleton ref to the currently-open rate-limit snackbar so a burst of
 * 429s (e.g. a forkJoin hitting the limiter) opens ONE toast, not N.
 * Cleared when the toast dismisses itself so the next real rate-limit
 * event reopens it.
 */
let activeRateLimitSnackbar: MatSnackBarRef<RateLimitSnackbarComponent> | null = null;

/**
 * Upper bound on the countdown we show. The server may set Retry-After
 * to the full hourly-window remainder (thousands of seconds) — that's a
 * hostile UX. Cap the VISIBLE countdown; the server still rejects until
 * its real cooldown elapses, but the user stops staring at a 35-minute
 * timer. 90s matches a typical operator's retry cadence.
 */
const MAX_VISIBLE_RETRY_SECONDS = 90;

/**
 * Phase E2 / Gap 43 — parse the RFC 7231 Retry-After header.
 *
 * Two legal formats:
 *   - delta-seconds: a non-negative integer ("120" = 120 seconds from now).
 *   - HTTP-date: e.g. "Wed, 21 Oct 2015 07:28:00 GMT" — compute delta.
 *
 * Returns the number of seconds to wait, or a sensible fallback if the
 * header is missing or unparseable. Clamped to [1, 3600] so we don't
 * show "wait 0 seconds" (useless) or "wait 14 hours" (a hostile server;
 * show a short toast instead).
 */
function parseRetryAfter(error: HttpErrorResponse): number {
  const FALLBACK_SECONDS = 30;
  const MIN_SECONDS = 1;
  const MAX_SECONDS = 3600;

  const raw = error?.headers?.get?.('Retry-After');
  if (!raw) return FALLBACK_SECONDS;

  // delta-seconds form
  const asInt = Number.parseInt(raw, 10);
  if (Number.isFinite(asInt) && asInt >= 0) {
    return Math.max(MIN_SECONDS, Math.min(MAX_SECONDS, asInt));
  }

  // HTTP-date form
  const asDate = Date.parse(raw);
  if (!Number.isNaN(asDate)) {
    const deltaSec = Math.ceil((asDate - Date.now()) / 1000);
    if (deltaSec > 0) {
      return Math.max(MIN_SECONDS, Math.min(MAX_SECONDS, deltaSec));
    }
  }

  return FALLBACK_SECONDS;
}

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const snack = inject(MatSnackBar);

  // Telemetry beacons (web vitals, client errors) are best-effort
  // fire-and-forget. Any failure must be silenced — toasts, countdown
  // snackbars, AND the global 5xx retry are all hostile UX for a
  // background beacon the operator never asked for.
  const isTelemetry = req.url.includes('/api/telemetry/');

  return next(req).pipe(
    // Retry once on 5xx with a 1-second delay — covers transient server blips.
    // Only retries idempotent methods (GET, HEAD, OPTIONS) to avoid side effects.
    // Telemetry is excluded entirely so we don't double-spam the limiter.
    retry({
      count: 1,
      delay: (error) => {
        if (isTelemetry) {
          return throwError(() => error);
        }
        const isRetryable = error?.status >= 500 && ['GET', 'HEAD', 'OPTIONS'].includes(req.method);
        if (isRetryable) {
          return timer(1000);
        }
        return throwError(() => error);
      },
    }),
    catchError((error: HttpErrorResponse) => {
      // Telemetry: silently swallow EVERY failure (429, 5xx, 0/network).
      if (isTelemetry) {
        return throwError(() => error);
      }

      const status = error?.status;

      // Auth interceptor handles 401/403 — don't show duplicate toasts
      if (status === 401 || status === 403) {
        return throwError(() => error);
      }

      // Gap 43 — 429 gets a live countdown snackbar instead of a flat toast.
      if (status === 429) {
        const rawSeconds = parseRetryAfter(error);
        const seconds = Math.min(rawSeconds, MAX_VISIBLE_RETRY_SECONDS);

        // Dedupe: if a rate-limit toast is already up, don't stack. A
        // single burst (forkJoin of 27 settings) can emit N 429s at once
        // — stacking N snackbars would bury real UI for minutes.
        if (!activeRateLimitSnackbar) {
          activeRateLimitSnackbar = snack.openFromComponent<
            RateLimitSnackbarComponent,
            RateLimitSnackbarData
          >(
            RateLimitSnackbarComponent,
            {
              duration: (seconds + 1) * 1000,
              data: { seconds },
              panelClass: ['rate-limit-snackbar'],
            },
          );
          activeRateLimitSnackbar.afterDismissed().subscribe(() => {
            activeRateLimitSnackbar = null;
          });
        }
        return throwError(() => error);
      }

      let message = 'An unexpected error occurred';

      if (status === 0) {
        // Distinguish network error causes
        const errorMsg = error?.message?.toLowerCase() ?? '';
        if (errorMsg.includes('cors')) {
          message = 'Cross-origin request blocked — contact support';
        } else {
          message = 'Network error — check your connection';
        }
      } else if (status === 404) {
        message = 'Resource not found';
      } else if (status >= 500) {
        message = 'Server error — please try again later';
      }

      snack.open(message, 'Dismiss', { duration: 5000 });
      return throwError(() => error);
    })
  );
};
