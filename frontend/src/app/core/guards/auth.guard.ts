import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { filter, switchMap, take, map, timeout, catchError, of } from 'rxjs';
import { AuthService } from '../services/auth.service';

/** Maximum time to wait for the startup auth check before redirecting. */
const AUTH_CHECK_TIMEOUT_MS = 5000;

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  // Wait for the startup token-check to complete before deciding.
  // Timeout after 5 seconds to prevent the user getting stuck if
  // initAuth() hangs (e.g. backend unreachable during startup).
  return auth.isChecking$.pipe(
    filter(checking => !checking),
    take(1),
    timeout(AUTH_CHECK_TIMEOUT_MS),
    switchMap(() => auth.isLoggedIn$),
    take(1),
    map(isLoggedIn => {
      if (isLoggedIn) return true;
      return router.createUrlTree(['/login'], {
        queryParams: { returnUrl: state.url },
      });
    }),
    catchError(() => {
      // Timeout or unexpected error — redirect to login
      return of(router.createUrlTree(['/login'], {
        queryParams: { returnUrl: state.url },
      }));
    })
  );
};
