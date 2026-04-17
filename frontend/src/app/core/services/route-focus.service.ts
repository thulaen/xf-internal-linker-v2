import { Injectable, DestroyRef, inject } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';

/**
 * Phase U2 / Gap 22 — Move keyboard focus to the main heading on every
 * route change.
 *
 * Without this, a Tab press after clicking a nav link falls through to
 * whatever the Router rendered first — usually a bunch of logos and
 * breadcrumbs before reaching the page content. Keyboard users spend a
 * dozen keypresses getting past chrome before they find the new page.
 *
 * Rule:
 *   1. After `NavigationEnd`, look for `<main>`, then `<h1>`, then
 *      `<[role="main"]>` in that order. First match wins.
 *   2. Set `tabindex="-1"` temporarily so non-focusable elements accept
 *      `.focus()`, clean it up on blur.
 *   3. Respect opt-out via `data-route-focus="skip"` on the landing
 *      element so routes with a custom focus target (e.g. a search box)
 *      can take control.
 *   4. Opt-out via `data-route-focus-target="selector"` on any ancestor
 *      lets a route redirect focus to a specific element.
 *
 * Works with Phase U1 / Gap 23 RouteAnnouncer (they do complementary
 * jobs — announcer tells screen readers WHAT page loaded, focus service
 * moves the keyboard caret TO it).
 */
@Injectable({ providedIn: 'root' })
export class RouteFocusService {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  private started = false;

  /** Call once from the root component. Safe to call multiple times. */
  start(): void {
    if (this.started) return;
    this.started = true;

    const sub = this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe(() => {
        // rAF ensures the new route has rendered before we search for
        // its focus target.
        requestAnimationFrame(() => this.moveFocus());
      });

    this.destroyRef.onDestroy(() => sub.unsubscribe());
  }

  /**
   * Public so feature pages can re-call it after an in-page
   * mode change (e.g., switching dashboard tabs).
   */
  moveFocus(): void {
    const target = this.resolveTarget();
    if (!target) return;

    // Elements that aren't natively focusable need tabindex="-1" to
    // accept programmatic focus. Use -1 (not 0) so they don't appear
    // in the Tab order afterwards.
    const hadTabIndex = target.hasAttribute('tabindex');
    if (!hadTabIndex) {
      target.setAttribute('tabindex', '-1');
      // Remove on blur so the DOM stays clean — the next route will
      // set its own.
      const cleanup = () => {
        target.removeAttribute('tabindex');
        target.removeEventListener('blur', cleanup);
      };
      target.addEventListener('blur', cleanup, { once: true });
    }

    try {
      target.focus({ preventScroll: true });
    } catch {
      // focus() can throw in rare DOM states; silently ignore.
    }
  }

  private resolveTarget(): HTMLElement | null {
    // 1. Explicit opt-out on an ancestor.
    const optOut = document.querySelector<HTMLElement>('[data-route-focus="skip"]');
    if (optOut) return null;

    // 2. Explicit target override on any ancestor.
    const overrideHost = document.querySelector<HTMLElement>('[data-route-focus-target]');
    if (overrideHost) {
      const selector = overrideHost.getAttribute('data-route-focus-target');
      if (selector) {
        const explicit = document.querySelector<HTMLElement>(selector);
        if (explicit) return explicit;
      }
    }

    // 3. Standard landmarks in priority order.
    return (
      document.querySelector<HTMLElement>('main') ??
      document.querySelector<HTMLElement>('h1') ??
      document.querySelector<HTMLElement>('[role="main"]')
    );
  }
}
