import { Injectable, computed, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { NavigationEnd, Router, ActivatedRouteSnapshot } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs/operators';

/**
 * Phase NV / Gap 146 — Recent pages history.
 *
 * Maintains the last `MAX` pages the user visited (deduped by URL with
 * the latest visit floating to the top). Persisted to localStorage so
 * the menu still shows after a refresh.
 *
 * Excluded routes:
 *   • /login                      — meaningless to revisit
 *   • the current page itself     — prevents "click recent → reload"
 *
 * Each entry stores: url, label (resolved like breadcrumbs), and a
 * Unix-ms `visitedAt` for relative-time labels in the menu.
 */
export interface RecentPage {
  url: string;
  label: string;
  visitedAt: number;
}

const MAX = 5;
const STORAGE_KEY = 'recentpages.v1';
const EXCLUDE_PREFIXES = ['/login'];

@Injectable({ providedIn: 'root' })
export class RecentPagesService {
  private router = inject(Router);
  private doc = inject(DOCUMENT);

  private readonly _pages = signal<RecentPage[]>(this.load());

  /** All recent pages oldest-to-newest. */
  readonly pages = computed(() => this._pages());

  /** Recent pages excluding the current URL — what the menu actually shows. */
  readonly menuPages = computed(() =>
    this._pages().filter((p) => p.url !== this.router.url),
  );

  constructor() {
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe((e) => this.record(e.urlAfterRedirects));
  }

  clear(): void {
    this._pages.set([]);
    this.persist();
  }

  private record(url: string): void {
    if (!url) return;
    if (EXCLUDE_PREFIXES.some((p) => url === p || url.startsWith(p + '/'))) return;

    const label = this.resolveLabel(url);
    const now = Date.now();

    const next: RecentPage[] = [{ url, label, visitedAt: now }];
    for (const existing of this._pages()) {
      if (existing.url === url) continue;
      next.push(existing);
      if (next.length >= MAX) break;
    }
    this._pages.set(next);
    this.persist();
  }

  private resolveLabel(url: string): string {
    // Walk the active snapshot tree, prefer the deepest route's title /
    // data.breadcrumb. Fallback: prettify the last segment.
    const root = this.router.routerState.snapshot.root;
    let cursor: ActivatedRouteSnapshot | null = root;
    let label = '';
    while (cursor) {
      const t = cursor.routeConfig?.title;
      const bc = cursor.data?.['breadcrumb'];
      if (typeof bc === 'string' && bc.length > 0) label = bc;
      else if (typeof t === 'string' && t.length > 0) {
        label = t.replace(/\s*[—-]\s*XF Internal Linker\s*$/i, '').trim();
      }
      cursor = cursor.firstChild ?? null;
    }
    if (label) return label;
    const segs = url.split('?')[0].split('#')[0].split('/').filter(Boolean);
    const last = segs[segs.length - 1] ?? 'Home';
    return last
      .split('-')
      .map((p) => (p.length > 0 ? p[0].toUpperCase() + p.slice(1) : p))
      .join(' ');
  }

  private persist(): void {
    try {
      this.doc.defaultView?.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(this._pages()),
      );
    } catch {
      /* QuotaExceeded / SecurityError — ignore */
    }
  }

  private load(): RecentPage[] {
    try {
      const raw = this.doc.defaultView?.localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter(
          (p): p is RecentPage =>
            !!p &&
            typeof p === 'object' &&
            typeof (p as RecentPage).url === 'string' &&
            typeof (p as RecentPage).label === 'string' &&
            typeof (p as RecentPage).visitedAt === 'number',
        )
        .slice(0, MAX);
    } catch {
      return [];
    }
  }
}
