import { HttpInterceptorFn, HttpErrorResponse, HttpEvent, HttpRequest, HttpHandlerFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, from, switchMap, throwError } from 'rxjs';

import { TOKEN_KEY } from '../services/auth.service';
import { SessionReauthService } from '../services/session-reauth.service';

const TOKEN_ENDPOINT = '/api/auth/token/';

/**
 * Authorization header + 401 handling.
 *
 * Phase U1 / Gap 14 — on a 401 response the interceptor prompts the user
 * to re-authenticate in a dialog instead of hard-redirecting to /login.
 * If they succeed, the original request is retried with the new token
 * and the user never leaves their current page. If they cancel, we fall
 * back to the legacy redirect so the app still reaches a clean login
 * state.
 *
 * The re-auth promise is deduplicated inside `SessionReauthService`: N
 * parallel 401s share one dialog instance, then each inflight call
 * retries independently.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const reauth = inject(SessionReauthService);

  // Never attach auth header to the token endpoint itself
  if (req.url.includes(TOKEN_ENDPOINT)) {
    return next(req);
  }

  return sendWithAuth(req, next).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401) {
        return throwError(() => error);
      }

      // On the login page, the legacy behaviour (bounce to login, clear
      // token) is the right one — don't prompt a dialog on a page that
      // IS the login.
      if (router.url.startsWith('/login')) {
        localStorage.removeItem(TOKEN_KEY);
        return throwError(() => error);
      }

      // Gap 14 — show a re-auth dialog. If the user succeeds, retry the
      // original request once with the new token. If they cancel, we
      // fall through to the legacy redirect.
      return from(reauth.prompt()).pipe(
        switchMap((recovered) => {
          if (recovered) {
            return sendWithAuth(req, next);
          }
          // Cancel path: clear stale token and bounce to /login so the
          // app reaches a clean state.
          localStorage.removeItem(TOKEN_KEY);
          router.navigate(['/login'], {
            queryParams: { returnUrl: router.url },
          });
          return throwError(() => error);
        }),
      );
    }),
  );
};

/**
 * Attach the current (possibly refreshed) Authorization header and
 * forward. Extracted so the 401-retry path can re-use the same logic
 * with the NEW token that the re-auth dialog just wrote to localStorage.
 */
function sendWithAuth(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
): Observable<HttpEvent<unknown>> {
  const token = localStorage.getItem(TOKEN_KEY);
  const authReq = token
    ? req.clone({ setHeaders: { Authorization: `Token ${token}` } })
    : req;
  return next(authReq);
}
