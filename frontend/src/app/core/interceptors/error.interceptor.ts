/**
 * Error interceptor — catches HTTP errors and shows friendly notifications.
 * 401/403 are handled by the auth interceptor, so we skip them here
 * to avoid duplicate toasts and conflicting navigation.
 *
 * Enterprise-grade features:
 * - Single retry on 5xx errors (covers transient blips)
 * - 429 rate-limit handling
 * - Network error cause distinction
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, retry, throwError, timer } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const snack = inject(MatSnackBar);

  return next(req).pipe(
    // Retry once on 5xx with a 1-second delay — covers transient server blips.
    // Only retries idempotent methods (GET, HEAD, OPTIONS) to avoid side effects.
    retry({
      count: 1,
      delay: (error) => {
        const isRetryable = error?.status >= 500 && ['GET', 'HEAD', 'OPTIONS'].includes(req.method);
        if (isRetryable) {
          return timer(1000);
        }
        return throwError(() => error);
      },
    }),
    catchError((error) => {
      const status = error?.status;

      // Auth interceptor handles 401/403 — don't show duplicate toasts
      if (status === 401 || status === 403) {
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
      } else if (status === 429) {
        message = 'Too many requests — please wait a moment';
      } else if (status >= 500) {
        message = 'Server error — please try again later';
      }

      snack.open(message, 'Dismiss', { duration: 5000 });
      return throwError(() => error);
    })
  );
};
