import { Injectable, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, ActivatedRouteSnapshot } from '@angular/router';
import { Title } from '@angular/platform-browser';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs/operators';

/**
 * Phase NV / Gap 143 — Breadcrumb trail.
 *
 * Walks the active ActivatedRouteSnapshot tree on every NavigationEnd and
 * produces a list of {label, url} crumbs. The first crumb is always
 * "Home" → /dashboard. Subsequent crumbs come from each route segment.
 *
 * Labels resolve in this order of preference:
 *   1. `data.breadcrumb` literal on the route
 *   2. The matched route's `title` (with the " — XF Internal Linker" suffix
 *      stripped, since that's repetitive in a breadcrumb)
 *   3. The path segment, title-cased ("link-health" → "Link Health")
 *
 * The BreadcrumbsComponent renders only when there are 3+ crumbs (i.e. the
 * current page is more than two levels deep), per the gap spec. Top-level
 * pages like /dashboard or /review intentionally render nothing.
 */
export interface Crumb {
  label: string;
  url: string;
  /** True for the last crumb (current page) — rendered as text, not a link. */
  current: boolean;
}

@Injectable({ providedIn: 'root' })
export class BreadcrumbService {
  private router = inject(Router);
  private titleService = inject(Title);

  private readonly _crumbs = signal<Crumb[]>([]);
  readonly crumbs = computed(() => this._crumbs());

  /** True when depth >2 — gates whether the breadcrumb bar renders at all. */
  readonly visible = computed(() => this._crumbs().length >= 3);

  constructor() {
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.rebuild());

    // Build once on init for refreshes that land mid-route.
    this.rebuild();
  }

  private rebuild(): void {
    const root = this.router.routerState.snapshot.root;
    const out: Crumb[] = [{ label: 'Home', url: '/dashboard', current: false }];

    let url = '';
    for (const seg of this.flattenRoute(root)) {
      const path = seg.routeConfig?.path;
      if (!path || path === '') continue;
      url += '/' + this.resolvePath(path, seg);
      out.push({
        label: this.resolveLabel(seg),
        url,
        current: false,
      });
    }

    if (out.length > 0) out[out.length - 1].current = true;
    // Drop the auto-Home if the user is already on /dashboard — single crumb is silly.
    if (out.length === 1 && out[0].url === '/dashboard') {
      this._crumbs.set([]);
      return;
    }
    this._crumbs.set(out);
  }

  /** Walk the route snapshot tree depth-first, returning each segment in order. */
  private flattenRoute(snapshot: ActivatedRouteSnapshot): ActivatedRouteSnapshot[] {
    const out: ActivatedRouteSnapshot[] = [];
    let cursor: ActivatedRouteSnapshot | undefined = snapshot.firstChild ?? undefined;
    while (cursor) {
      out.push(cursor);
      cursor = cursor.firstChild ?? undefined;
    }
    return out;
  }

  /** Substitute :param tokens with the actual matched values. */
  private resolvePath(path: string, snapshot: ActivatedRouteSnapshot): string {
    if (!path.includes(':')) return path;
    return path
      .split('/')
      .map((part) =>
        part.startsWith(':') ? snapshot.params[part.slice(1)] ?? part : part,
      )
      .join('/');
  }

  private resolveLabel(snapshot: ActivatedRouteSnapshot): string {
    const data = snapshot.data ?? {};
    if (typeof data['breadcrumb'] === 'string' && data['breadcrumb'].length > 0) {
      return data['breadcrumb'];
    }
    const routeTitle = snapshot.routeConfig?.title;
    if (typeof routeTitle === 'string' && routeTitle.length > 0) {
      return routeTitle.replace(/\s*[—-]\s*XF Internal Linker\s*$/i, '').trim();
    }
    const path = snapshot.routeConfig?.path ?? '';
    return this.prettify(path);
  }

  private prettify(path: string): string {
    if (!path) return '';
    return path
      .split('-')
      .map((p) => (p.length > 0 ? p[0].toUpperCase() + p.slice(1) : p))
      .join(' ');
  }
}
