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

/**
 * SonarSource ``typescript:S3776`` refactor — the original
 * ``errorInterceptor`` body interleaved retry policy, status routing,
 * 429 dedup and server-message extraction.  Each concern is now its
 * own helper so the interceptor body stays under the cognitive-
 * complexity ceiling.  Behaviour is unchanged.
 */

/** Decide whether to wait 1s and retry, or surface the error to the
 *  catchError below.  Telemetry never retries (would double-spam the
 *  limiter); only idempotent 5xx requests retry. */
function _retryDelayStrategy(
  error: HttpErrorResponse,
  method: string,
  isTelemetry: boolean,
) {
  if (isTelemetry) return throwError(() => error);
  const isIdempotent = ['GET', 'HEAD', 'OPTIONS'].includes(method);
  const isRetryable = error?.status >= 500 && isIdempotent;
  return isRetryable ? timer(1000) : throwError(() => error);
}

/** Open the rate-limit countdown snackbar (once) when a 429 lands.
 *  Dedupes against a module-level singleton ref so a burst doesn't
 *  stack multiple snackbars. */
function _showRateLimitSnackbar(error: HttpErrorResponse, snack: MatSnackBar): void {
  const rawSeconds = parseRetryAfter(error);
  const seconds = Math.min(rawSeconds, MAX_VISIBLE_RETRY_SECONDS);
  if (activeRateLimitSnackbar) return;

  activeRateLimitSnackbar = snack.openFromComponent<
    RateLimitSnackbarComponent,
    RateLimitSnackbarData
  >(RateLimitSnackbarComponent, {
    duration: (seconds + 1) * 1000,
    data: { seconds },
    panelClass: ['rate-limit-snackbar'],
  });
  activeRateLimitSnackbar.afterDismissed().subscribe(() => {
    activeRateLimitSnackbar = null;
  });
}

/** Pick a plain-English fallback message for network errors / known
 *  status codes.  Server-supplied messages overlay this later. */
function _messageForNetworkOrStatus(error: HttpErrorResponse, status: number): string {
  if (status === 0) {
    const errorMsg = error?.message?.toLowerCase() ?? '';
    return errorMsg.includes('cors')
      ? 'Cross-origin request blocked — contact support'
      : 'Network error — check your connection';
  }
  if (status === 404) return 'Resource not found';
  if (status >= 500) return 'Server error — please try again later';
  return 'An unexpected error occurred';
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
      delay: (error) => _retryDelayStrategy(error, req.method, isTelemetry),
    }),
    catchError((error: HttpErrorResponse) => {
      const status = error?.status;
      // Telemetry: silently swallow EVERY failure (429, 5xx, 0/network).
      // Auth interceptor handles 401/403 — don't show duplicate toasts.
      if (isTelemetry || status === 401 || status === 403) {
        return throwError(() => error);
      }
      // Gap 43 — 429 gets a live countdown snackbar instead of a flat toast.
      if (status === 429) {
        _showRateLimitSnackbar(error, snack);
        return throwError(() => error);
      }

      // Prefer the server-supplied error detail when DRF returned one;
      // fall back to the network/status mapping.
      const message =
        extractServerErrorMessage(error) ?? _messageForNetworkOrStatus(error, status);
      snack.open(message, 'Dismiss', { duration: 5000 });
      return throwError(() => error);
    }),
  );
};

/**
 * Pull a human-readable message out of a DRF error body. Returns null
 * when nothing usable is present so the caller falls back to the
 * status-derived default. Caps the result at 240 chars so an overly
 * verbose backend traceback can't overflow the snackbar.
 *
 * SonarSource ``typescript:S3776`` second-round refactor (2026-05-22):
 * the body-parsing logic is split into three named helpers so this
 * dispatcher stays well under the cognitive-complexity ceiling (15).
 */
function extractServerErrorMessage(error: HttpErrorResponse): string | null {
  const body = error?.error;
  if (!body) return null;
  if (typeof body === 'string' && body.trim().length > 0) {
    return clampMessage(body.trim());
  }
  if (typeof body !== 'object') return null;
  const record = body as Record<string, unknown>;
  return (
    _extractDetailString(record) ??
    _extractMessageString(record) ??
    _findFirstStringInBody(record)
  );
}

/** Pull the DRF `detail` field — either a string or a string array. */
function _extractDetailString(body: Record<string, unknown>): string | null {
  const detail = body['detail'];
  if (typeof detail === 'string' && detail.trim()) {
    return clampMessage(detail.trim());
  }
  if (Array.isArray(detail) && typeof detail[0] === 'string') {
    return clampMessage(detail[0]);
  }
  return null;
}

/** Pull a generic `message` field. */
function _extractMessageString(body: Record<string, unknown>): string | null {
  const messageField = body['message'];
  if (typeof messageField === 'string' && messageField.trim()) {
    return clampMessage(messageField.trim());
  }
  return null;
}

/** Field-level errors: `{ username: ["already taken"] }`. Pick the first
 *  string found so the user sees the most-relevant validation hint. */
function _findFirstStringInBody(body: Record<string, unknown>): string | null {
  for (const value of Object.values(body)) {
    const candidate = _valueAsString(value);
    if (candidate !== null) return candidate;
  }
  return null;
}

/** Coerce a single field-level value to its first usable string, or null. */
function _valueAsString(value: unknown): string | null {
  if (Array.isArray(value) && typeof value[0] === 'string' && value[0].trim()) {
    return clampMessage(value[0]);
  }
  if (typeof value === 'string' && value.trim()) {
    return clampMessage(value.trim());
  }
  return null;
}

function clampMessage(message: string): string {
  return message.length > 240 ? message.slice(0, 237) + '…' : message;
}
