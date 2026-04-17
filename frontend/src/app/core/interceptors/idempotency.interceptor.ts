import { HttpHandlerFn, HttpInterceptorFn, HttpRequest } from '@angular/common/http';

/**
 * Phase GK1 / Gap 208 — Idempotency keys on POSTs.
 *
 * Stamps every `POST` that isn't already carrying `Idempotency-Key`
 * with a fresh UUID. The backend dedup layer uses this header to
 * short-circuit accidental multi-fire (double-click, network retry,
 * pull-to-refresh) so the same action never happens twice.
 *
 * Skips:
 *   - Non-POST methods.
 *   - Requests that already declare `Idempotency-Key` (caller knows best).
 *   - Any request whose URL matches the opt-out prefixes below (login,
 *     CSRF probes) — stamping these would make them uncacheable without
 *     upside.
 */

const _OPT_OUT_PREFIXES: readonly string[] = [
  '/api/auth/token/',
  '/api/auth/login/',
  '/api/telemetry/',
];

function _generateKey(): string {
  // Prefer crypto.randomUUID when available — saves 30+ chars vs Math.random.
  const g = (globalThis as unknown) as { crypto?: { randomUUID?: () => string } };
  if (g.crypto?.randomUUID) return g.crypto.randomUUID();
  return (
    'idem-' +
    Date.now().toString(36) +
    '-' +
    Math.random().toString(36).slice(2, 10) +
    Math.random().toString(36).slice(2, 10)
  );
}

export const idempotencyInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
) => {
  if (req.method !== 'POST') return next(req);
  if (req.headers.has('Idempotency-Key')) return next(req);
  if (_OPT_OUT_PREFIXES.some((p) => req.url.startsWith(p))) return next(req);

  const stamped = req.clone({
    setHeaders: { 'Idempotency-Key': _generateKey() },
  });
  return next(stamped);
};
