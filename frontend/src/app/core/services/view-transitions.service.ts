import { DestroyRef, Injectable, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';

/**
 * Phase F1 / Gap 79 + 81 — View Transitions API integration.
 *
 * The browser's native `document.startViewTransition()` interpolates
 * CSS state between two DOM snapshots — the one that existed when
 * `startViewTransition()` was called, and the one produced by the
 * callback. We wrap Angular router navigations in a transition so:
 *
 *   - Gap 79: A soft fade / slide between routes (instead of instant
 *     swap) without CSS animations per component.
 *   - Gap 81: "Shared element" transitions where a card on the
 *     dashboard flies out into its detail route, when both elements
 *     share `view-transition-name: <stable-id>` in CSS.
 *
 * Browsers without the API (Firefox as of 2026-Q1, Safari rolling in)
 * just fall through to a normal synchronous navigation.
 *
 * Implementation:
 *   - On NavigationStart, if the API is available, we grab a deferred
 *     transition callback and wait on the router's NavigationEnd to
 *     resolve it. The browser keeps the "from" snapshot around until
 *     our callback finishes, so Angular has time to render the new
 *     route before the crossfade starts.
 *   - Honours `prefers-reduced-motion: reduce` — skips the transition
 *     entirely on that setting.
 *
 * Call `start()` once from app bootstrap. Safe no-op on unsupported
 * browsers; safe to call repeatedly.
 */
@Injectable({ providedIn: 'root' })
export class ViewTransitionsService {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private started = false;

  start(): void {
    if (this.started) return;
    this.started = true;
    if (!this.supported()) return;
    if (this.reducedMotion()) return;

    let endTransition: ((_: unknown) => void) | null = null;

    this.router.events
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((e) => {
        if (e instanceof NavigationStart) {
          // `startViewTransition` accepts a callback that runs the DOM
          // change. We defer the actual "finished" signal until
          // NavigationEnd by returning a promise that the NavigationEnd
          // branch resolves.
          try {
            const doc = document as unknown as {
              startViewTransition?: (cb: () => Promise<unknown>) => unknown;
            };
            doc.startViewTransition?.(() => {
              return new Promise((resolve) => {
                endTransition = resolve;
              });
            });
          } catch {
            // Safari sometimes throws when a transition is already in
            // flight — swallow and let navigation proceed normally.
          }
        } else if (e instanceof NavigationEnd) {
          if (endTransition) {
            // Give Angular one frame to paint the new route before
            // resolving; otherwise the crossfade fires too early and
            // looks like no transition at all.
            requestAnimationFrame(() => {
              if (endTransition) {
                endTransition(undefined);
                endTransition = null;
              }
            });
          }
        }
      });
  }

  private supported(): boolean {
    return (
      typeof document !== 'undefined' &&
      typeof (document as unknown as { startViewTransition?: unknown })
        .startViewTransition === 'function'
    );
  }

  private reducedMotion(): boolean {
    return (
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
  }
}
