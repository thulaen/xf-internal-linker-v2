import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { TOKEN_KEY } from '../services/auth.service';

const TOKEN_ENDPOINT = '/api/auth/token/';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);

  // Never attach auth header to the token endpoint itself
  if (req.url.includes(TOKEN_ENDPOINT)) {
    return next(req);
  }

  const token = localStorage.getItem(TOKEN_KEY);
  const authReq = token
    ? req.clone({ setHeaders: { Authorization: `Token ${token}` } })
    : req;

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401) {
        // Only redirect if we're not already on the login page.
        // This avoids the fragile static-flag approach and naturally
        // handles parallel 401 responses without race conditions.
        const onLoginPage = router.url.startsWith('/login');
        if (!onLoginPage) {
          localStorage.removeItem(TOKEN_KEY);
          router.navigate(['/login'], {
            queryParams: { returnUrl: router.url },
          });
        }
      }
      return throwError(() => error);
    })
  );
};
