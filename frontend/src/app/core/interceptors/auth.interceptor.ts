/**
 * Auth interceptor — attaches CSRF token and session credentials to all API requests.
 * Full auth implementation added in Phase 4.
 */

import { HttpInterceptorFn } from '@angular/common/http';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  // Phase 4: attach auth token / CSRF token here
  return next(req);
};
