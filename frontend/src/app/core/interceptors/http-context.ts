import { HttpContext, HttpContextToken } from '@angular/common/http';

/**
 * Opt-out token for the global error interceptor's toast. When a caller
 * knows a request may legitimately 404 / 500 (e.g. a not-yet-deployed
 * backend endpoint, or a capability probe that is expected to fail on
 * some installs), it can set this context token to `true` and the
 * interceptor will swallow the toast silently. The error still bubbles
 * up to the caller's `catchError`, so local fallback logic keeps working.
 *
 * Usage:
 *   import { silentHttpErrors } from '.../http-context';
 *   this.http.get('/api/foo/', { context: silentHttpErrors() })
 *     .pipe(catchError(() => of(null)))
 *     .subscribe(...)
 */
export const SILENT_HTTP_ERRORS = new HttpContextToken<boolean>(() => false);

/** Convenience: pre-built `HttpContext` with silencing enabled. */
export function silentHttpErrors(): HttpContext {
  return new HttpContext().set(SILENT_HTTP_ERRORS, true);
}
