/**
 * Error interceptor — catches HTTP errors and shows friendly notifications.
 * Full error handling implementation added in Phase 4.
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    catchError((error) => {
      // Phase 4: show snackbar, handle 401 redirects, log errors
      console.error('HTTP Error:', error);
      return throwError(() => error);
    })
  );
};
