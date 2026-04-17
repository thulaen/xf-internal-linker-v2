/**
 * Phase OB / Gap 137 — W3C traceparent HTTP interceptor.
 *
 * Adds a `traceparent` header to every outgoing HTTP request so that
 * backend logs, GlitchTip / Sentry spans, and Celery task traces can
 * be stitched into a single user-action timeline.
 *
 * Header format (W3C Trace Context):
 *
 *   00-<32-hex-trace-id>-<16-hex-span-id>-01
 *
 *   - version: "00" (this is the only version defined today)
 *   - trace-id: 32 hex chars (128 bits) — one per top-level action
 *   - parent-id: 16 hex chars (64 bits) — one per request inside that action
 *   - flags: "01" = sampled
 *
 * Every action starts a new trace-id; each HTTP call gets a fresh
 * span-id. The top-level trace-id is recycled across same-action
 * fanout calls (e.g. the dashboard hits /api/dashboard/,
 * /api/dashboard/today-actions/, /api/dashboard/what-changed/ in
 * parallel — they share one trace-id).
 *
 * Scope limits:
 *   - We use crypto.getRandomValues for the hex IDs. No cross-origin
 *     traces — Angular's `withCredentials` already blocks that.
 *   - No `tracestate` today; backend parses `traceparent` only.
 *   - Action grouping is timer-based: all requests within a rolling
 *     200ms window share the same trace-id. Crude but good enough
 *     to cluster a dashboard fan-out without a proper OpenTelemetry
 *     context manager.
 */

import { HttpInterceptorFn } from '@angular/common/http';

let currentTraceId = '';
let currentTraceExpiresAt = 0;
const ACTION_WINDOW_MS = 200;

export const traceparentInterceptor: HttpInterceptorFn = (req, next) => {
  // Skip external origins — only same-origin gets the header.
  const isAbsolute = /^https?:\/\//i.test(req.url);
  if (isAbsolute && typeof location !== 'undefined') {
    try {
      const target = new URL(req.url);
      if (target.origin !== location.origin) {
        return next(req);
      }
    } catch {
      return next(req);
    }
  }

  const now = Date.now();
  if (now > currentTraceExpiresAt) {
    currentTraceId = randomHex(32);
  }
  currentTraceExpiresAt = now + ACTION_WINDOW_MS;

  const spanId = randomHex(16);
  const traceparent = `00-${currentTraceId}-${spanId}-01`;

  const withTrace = req.clone({
    setHeaders: {
      traceparent,
    },
  });
  return next(withTrace);
};

function randomHex(nibbles: number): string {
  // crypto.getRandomValues works in every browser we target.
  const bytes = new Uint8Array(nibbles / 2);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  let s = '';
  for (const b of bytes) s += b.toString(16).padStart(2, '0');
  return s;
}
