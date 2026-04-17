import { Injectable, inject, DestroyRef } from '@angular/core';
import { NavigationEnd, Router, ActivatedRoute } from '@angular/router';
import { Title } from '@angular/platform-browser';
import { filter } from 'rxjs/operators';

/**
 * Phase U1 / Gap 23 — Screen-reader route announcements.
 *
 * On every `NavigationEnd`, reads the route's `title` (set via the
 * Angular Router's built-in title strategy) and pushes it into a
 * shared `aria-live="polite"` region so screen-reader users hear the
 * page change. Sighted users see no visual change — the region is
 * clipped to 1×1 px off-screen.
 *
 * Only one live region per app — created lazily on first announcement
 * and re-used forever.
 *
 * Why polite (not assertive):
 *   - Route changes are informational, not urgent.
 *   - Polite announces in the next pause, which pairs well with users
 *     who are already navigating with their reader.
 *   - `ScrollAttentionService` (Phase GB / Gap 148) uses a separate
 *     polite region for urgent attention; they deliberately don't share
 *     a DOM node so one can be cleared without cancelling the other.
 */
@Injectable({ providedIn: 'root' })
export class RouteAnnouncerService {
  private readonly router = inject(Router);
  private readonly title = inject(Title);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  private liveRegion: HTMLElement | null = null;
  private started = false;

  /** Call once from the root component's `ngOnInit`. Safe to call
   *  multiple times — second invocation is a no-op. */
  start(): void {
    if (this.started) return;
    this.started = true;

    const sub = this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe(() => this.announceCurrent());

    this.destroyRef.onDestroy(() => sub.unsubscribe());
  }

  /** Manually announce an arbitrary message. Useful for flows that
   *  fake a route change without an actual NavigationEnd (e.g. tab
   *  switches within a single-route page). */
  announce(message: string): void {
    if (!message) return;
    const region = this.ensureLiveRegion();
    // Clear first so the same message twice still re-announces —
    // screen readers skip textContent that hasn't changed.
    region.textContent = '';
    window.setTimeout(() => {
      region.textContent = message;
    }, 20);
  }

  private announceCurrent(): void {
    const docTitle = this.title.getTitle();
    // Use the full document title when available — it includes both the
    // page name and the app suffix, which is what the Router builder
    // produces ("Dashboard — XF Internal Linker"). The part before
    // "—" is what a screen-reader user cares about, so split if present.
    const spoken = docTitle.split('—')[0].trim() || docTitle;
    if (spoken) {
      this.announce(`Navigated to ${spoken}`);
    }
  }

  private ensureLiveRegion(): HTMLElement {
    if (this.liveRegion && document.body.contains(this.liveRegion)) {
      return this.liveRegion;
    }
    const region = document.createElement('div');
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'true');
    region.setAttribute('role', 'status');
    region.className = 'route-announcer-region';
    // Visually-hidden but SR-accessible. Inline styles so the service is
    // self-contained and doesn't require a global CSS entry.
    Object.assign(region.style, {
      position: 'absolute',
      width: '1px',
      height: '1px',
      padding: '0',
      margin: '-1px',
      overflow: 'hidden',
      clip: 'rect(0 0 0 0)',
      whiteSpace: 'nowrap',
      border: '0',
    } as CSSStyleDeclaration);
    document.body.appendChild(region);
    this.liveRegion = region;
    return region;
  }
}
