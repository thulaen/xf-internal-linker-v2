import { Injectable, computed, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';

/**
 * Phase GK1 / Gap 196 — Route favoriting.
 *
 * Lets the operator "star" any route. Starred routes render at the
 * top of the sidenav via the star-section shown by `app.component`.
 * Stored in localStorage under `favroutes.v1`.
 */

export interface FavoriteRoute {
  /** Angular router URL (e.g. `/review?status=pending`). */
  url: string;
  /** Human label rendered in the sidenav. */
  label: string;
  /** Material-icon ligature. */
  icon: string;
  /** Unix-ms added timestamp — used to sort deterministically. */
  addedAt: number;
}

const STORAGE_KEY = 'favroutes.v1';
const MAX = 12;

@Injectable({ providedIn: 'root' })
export class RouteFavoritesService {
  private doc = inject(DOCUMENT);

  private readonly _entries = signal<FavoriteRoute[]>(this.load());

  /** Oldest-first — so newly-starred routes land at the bottom of the
   *  favorites block, matching how bookmarks accumulate in browsers. */
  readonly entries = computed(() => this._entries());

  isStarred(url: string): boolean {
    return this._entries().some((f) => f.url === url);
  }

  toggle(url: string, label: string, icon = 'star'): FavoriteRoute | null {
    if (this.isStarred(url)) {
      this.remove(url);
      return null;
    }
    return this.add(url, label, icon);
  }

  add(url: string, label: string, icon = 'star'): FavoriteRoute | null {
    if (this._entries().length >= MAX) return null;
    if (this.isStarred(url)) {
      return this._entries().find((f) => f.url === url) ?? null;
    }
    const entry: FavoriteRoute = {
      url,
      label,
      icon: icon || 'star',
      addedAt: Date.now(),
    };
    this._entries.set([...this._entries(), entry]);
    this.persist();
    return entry;
  }

  remove(url: string): void {
    const next = this._entries().filter((f) => f.url !== url);
    if (next.length === this._entries().length) return;
    this._entries.set(next);
    this.persist();
  }

  clear(): void {
    this._entries.set([]);
    this.persist();
  }

  private persist(): void {
    try {
      this.doc.defaultView?.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(this._entries()),
      );
    } catch {
      /* ignore */
    }
  }

  private load(): FavoriteRoute[] {
    try {
      const raw = this.doc.defaultView?.localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter(
          (e): e is FavoriteRoute =>
            !!e &&
            typeof e === 'object' &&
            typeof (e as FavoriteRoute).url === 'string' &&
            typeof (e as FavoriteRoute).label === 'string',
        )
        .slice(0, MAX);
    } catch {
      return [];
    }
  }
}
