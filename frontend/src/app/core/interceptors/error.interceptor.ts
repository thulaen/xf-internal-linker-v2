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
      } else if (status === 401 || status === 403) {
        // Show a "unauthorized" message but stay on the page. 
        // This satisfies the user's request to let the dropdown work while logged out.
        message = status === 401 ? 'Session expired — please reload' : 'Permission denied';
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
