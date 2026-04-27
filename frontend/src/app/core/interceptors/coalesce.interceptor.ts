/**
 * In-flight request coalescing interceptor.
 *
 * When multiple components fire the same authenticated GET within the
 * same tick (e.g. dashboard cards each calling `/api/dashboard/`), this
 * collapses them into a single network roundtrip. The first caller
 * triggers the fetch; every concurrent caller subscribes to the same
 * shared Observable and gets the same response.
 *
 * What this is NOT:
 *   - A stale cache. Once the request settles (success or error), the
 *     entry is dropped. The next caller starts a fresh request. So we
 *     never serve stale data and we never need invalidation.
 *   - A retry queue. Telemetry beacons and idempotent retries are
 *     handled elsewhere; this layer is concurrent-dedupe only.
 *
 * What it skips on purpose:
 *   - Non-GET requests. Mutating verbs (POST/PUT/PATCH/DELETE) are
 *     never deduped — two POSTs that look identical may both need to
 *     hit the server.
 *   - `/api/telemetry/`. Beacons are best-effort and fire-and-forget;
 *     the backend already absorbs duplicates.
 *   - Requests with the `X-Skip-Coalesce` request header (escape hatch
 *     for callers that need a fresh roundtrip even when one is in
 *     flight, e.g. an explicit "refresh" button).
 *
 * Why RxJS `share()` and not a hand-rolled Map<url, Subject>:
 *   `share()` already gives us multicast + reference-counted subscribe
 *   plus correct teardown when the upstream completes or errors. The
 *   only thing we add is the keying logic and the in-flight registry.
 */

import { HttpInterceptorFn, HttpRequest, HttpEvent } from '@angular/common/http';
import { Observable, finalize, share } from 'rxjs';

const inFlight = new Map<string, Observable<HttpEvent<unknown>>>();

const SKIP_COALESCE_HEADER = 'X-Skip-Coalesce';

function coalesceKey(req: HttpRequest<unknown>): string {
  // Method is always GET here (we filtered upstream) but include it
  // anyway so the key remains correct if we ever extend to HEAD.
  // urlWithParams already encodes the serialized query string.
  return `${req.method} ${req.urlWithParams}`;
}

function shouldCoalesce(req: HttpRequest<unknown>): boolean {
  if (req.method !== 'GET') return false;
  if (req.headers.has(SKIP_COALESCE_HEADER)) return false;
  if (req.url.includes('/api/telemetry/')) return false;
  return true;
}

export const coalesceInterceptor: HttpInterceptorFn = (req, next) => {
  if (!shouldCoalesce(req)) {
    // Strip the escape-hatch header so it never reaches the backend.
    if (req.headers.has(SKIP_COALESCE_HEADER)) {
      return next(req.clone({ headers: req.headers.delete(SKIP_COALESCE_HEADER) }));
    }
    return next(req);
  }

  const key = coalesceKey(req);
  const existing = inFlight.get(key);
  if (existing) {
    return existing;
  }

  // First caller for this key — start the request and register the
  // shared stream. Subsequent callers see `existing` above and reuse it.
  //
  // Cleanup contract: drop the registry entry exactly once when the
  // source observable terminates. `finalize` placed BEFORE `share()`
  // sees source-level termination (success, error, or refcount-zero
  // cancellation), so we don't need separate next/error branches and
  // we can't leak an entry on cancel paths. After the entry is gone,
  // the next caller falls through to a fresh `next(req)` call rather
  // than re-subscribing to a completed share.
  const shared = next(req).pipe(
    finalize(() => inFlight.delete(key)),
    share(),
  );

  inFlight.set(key, shared);
  return shared;
};
