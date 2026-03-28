/**
 * Error interceptor — catches HTTP errors and shows friendly notifications.
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
      let message = 'An unexpected error occurred';

      if (status === 0) {
        message = 'Network error — check your connection';
      } else if (status === 401) {
        message = 'Session expired — please reload';
      } else if (status === 403) {
        message = 'Permission denied';
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
