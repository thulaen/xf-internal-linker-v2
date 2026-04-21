import { DestroyRef, Injectable, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
} from '@angular/router';

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
 *   - On NavigationStart, if the API is available and no transition is
 *     currently in-flight, we grab a deferred transition callback and
 *     wait on the router's NavigationEnd to resolve it. The browser
 *     keeps the "from" snapshot around until our callback finishes,
 *     so Angular has time to render the new route before the
 *     crossfade starts.
 *   - If a previous transition is still active when a new navigation
 *     starts, skip the new one rather than calling the API recursively
 *     — the browser throws `InvalidStateError` in that case and leaves
 *     the old transition's promise dangling.
 *   - NavigationCancel and NavigationError both release the pending
 *     transition so a cancelled nav never pins the snapshot.
 *   - Honours `prefers-reduced-motion: reduce` — skips entirely.
 *
 * Call `start()` once from app bootstrap. Safe no-op on unsupported
 * browsers; safe to call repeatedly.
 */

interface ViewTransitionLike {
  skipTransition(): void;
  finished: Promise<void>;
}

type StartViewTransition = (cb: () => Promise<unknown>) => ViewTransitionLike;

@Injectable({ providedIn: 'root' })
export class ViewTransitionsService {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private started = false;

  /** Resolves the current transition's "finished" promise. */
  private endTransition: ((_: unknown) => void) | null = null;
  /** Handle to the in-flight ViewTransition object, if any. */
  private activeTransition: ViewTransitionLike | null = null;

  start(): void {
    if (this.started) return;
    this.started = true;
    if (!this.supported()) return;
    if (this.reducedMotion()) return;

    this.router.events
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((e) => {
        if (e instanceof NavigationStart) {
          // If a transition is already in-flight (slow route resolve,
          // rapid click-through), skip rather than chain. The browser
          // throws `InvalidStateError` when `startViewTransition` is
          // called while another transition is pending — the old
          // transition's promise would then dangle forever.
          if (this.activeTransition) {
            this.release();
          }
          try {
            const fn = (document as unknown as { startViewTransition?: StartViewTransition })
              .startViewTransition;
            if (!fn) return;
            this.activeTransition = fn.call(document, () =>
              new Promise<void>((resolve) => {
                this.endTransition = resolve as (_: unknown) => void;
              }),
            );
          } catch {
            // Some browsers still throw on edge cases (page hidden,
            // document frozen). Swallow — navigation proceeds normally.
            this.release();
          }
        } else if (e instanceof NavigationEnd) {
          if (this.endTransition) {
            // Give Angular one frame to paint the new route before
            // resolving; otherwise the crossfade fires too early and
            // looks like no transition at all.
            const end = this.endTransition;
            requestAnimationFrame(() => {
              end(undefined);
              if (this.endTransition === end) {
                this.endTransition = null;
                this.activeTransition = null;
              }
            });
          }
        } else if (e instanceof NavigationCancel || e instanceof NavigationError) {
          this.release();
        }
      });
  }

  /**
   * Abort any in-flight transition cleanly: skip the animation, resolve
   * the pending promise so the browser's internal state machine moves
   * on, and drop our references.
   */
  private release(): void {
    try {
      this.activeTransition?.skipTransition();
    } catch {
      // `skipTransition` throws if already finished — safe to ignore.
    }
    if (this.endTransition) {
      this.endTransition(undefined);
      this.endTransition = null;
    }
    this.activeTransition = null;
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
