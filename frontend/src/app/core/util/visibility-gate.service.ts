import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';
import {
  EMPTY,
  Observable,
  distinctUntilChanged,
  fromEvent,
  map,
  startWith,
  switchMap,
} from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Swaps a long-lived Observable for `EMPTY` whenever the user is signed out
 * or the tab is hidden. This is the single home for the pattern — do not
 * inline the logic in individual components.
 *
 * Why this matters: every RxJS `interval` / `timer` fires inside Angular's
 * zone and triggers change detection across the whole `OnPush` tree. A tab
 * that nobody is looking at shouldn't pay that cost, and a signed-out user
 * shouldn't pound the API with 403s. See `docs/PERFORMANCE.md` §13.
 *
 * Usage:
 *   private readonly gate = inject(VisibilityGateService);
 *   ngOnInit() {
 *     this.gate
 *       .whileLoggedInAndVisible(() => timer(0, 30_000).pipe(
 *         switchMap(() => this.http.get('/api/foo'))
 *       ))
 *       .pipe(takeUntilDestroyed(this.destroyRef))
 *       .subscribe(...);
 *   }
 */
@Injectable({ providedIn: 'root' })
export class VisibilityGateService {
  private readonly auth = inject(AuthService);
  private readonly document = inject(DOCUMENT);

  private readonly pageVisible$: Observable<boolean> = fromEvent(
    this.document,
    'visibilitychange',
  ).pipe(
    startWith(null),
    map(() => this.document.visibilityState === 'visible'),
    distinctUntilChanged(),
  );

  /**
   * Seed only emits while the user is signed in. On logout the inner stream
   * is cancelled cleanly; on login it re-starts from zero.
   */
  whileLoggedIn<T>(seed: () => Observable<T>): Observable<T> {
    return this.auth.isLoggedIn$.pipe(
      switchMap((loggedIn) => (loggedIn ? seed() : EMPTY)),
    );
  }

  /**
   * Seed only emits while the user is signed in AND the tab is visible.
   * Hiding the tab cancels the inner stream; showing it again re-starts it.
   */
  whileLoggedInAndVisible<T>(seed: () => Observable<T>): Observable<T> {
    return this.whileLoggedIn(() =>
      this.pageVisible$.pipe(
        switchMap((visible) => (visible ? seed() : EMPTY)),
      ),
    );
  }
}
