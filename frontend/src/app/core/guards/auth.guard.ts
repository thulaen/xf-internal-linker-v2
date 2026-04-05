import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { filter, switchMap, take, map } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  // Wait for the startup token-check to complete before deciding
  return auth.isChecking$.pipe(
    filter(checking => !checking),
    take(1),
    switchMap(() => auth.isLoggedIn$),
    take(1),
    map(isLoggedIn => {
      if (isLoggedIn) return true;
      return router.createUrlTree(['/login'], {
        queryParams: { returnUrl: state.url },
      });
    })
  );
};
