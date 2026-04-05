/**
 * Auth interceptor — attaches CSRF token and session credentials to all API requests.
 * Full auth implementation added in Phase 4.
 */

import { HttpInterceptorFn } from '@angular/common/http';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  // Get CSRF token from cookies 
  const getCookie = (name: string): string | null => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop()?.split(';').shift() ?? null;
    return null;
  };

  const csrfToken = getCookie('csrftoken');

  // Clone the request to add credentials (session cookie) and CSRF header
  let authReq = req.clone({
    withCredentials: true,
  });

  if (csrfToken && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(req.method)) {
    authReq = authReq.clone({
      setHeaders: {
        'X-CSRFToken': csrfToken,
      },
    });
  }

  return next(authReq);
};
