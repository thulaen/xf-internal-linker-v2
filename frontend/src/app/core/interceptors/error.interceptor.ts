/**
 * Error interceptor — catches HTTP errors and shows friendly notifications.
 * 401/403 are handled by the auth interceptor, so we skip them here
 * to avoid duplicate toasts and conflicting navigation.
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, throwError } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const snack = inject(MatSnackBar);

  return next(req).pipe(
    catchError((error) => {
      const status = error?.status;

      // Auth interceptor handles 401/403 — don't show duplicate toasts
      if (status === 401 || status === 403) {
        return throwError(() => error);
      }

      let message = 'An unexpected error occurred';

      if (status === 0) {
        message = 'Network error — check your connection';
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
