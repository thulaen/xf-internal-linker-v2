import { Injectable, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';

/**
 * Phase GK2 / Gap 225 + Gap 246 — Filter persistence across sessions.
 *
 * Complements Gap 17 (query-param state): query params are great for
 * sharing links, but they don't survive the user typing a fresh URL.
 * This service writes the filter snapshot to localStorage keyed by a
 * stable `pageId`, so when the operator returns to the page the
 * previous filters rehydrate.
 *
 * Gap 246 (cross-tab sync via localStorage): because we write to
 * localStorage, the `storage` event fires in other tabs — the
 * `subscribe(pageId, fn)` helper wraps that so two open tabs on the
 * same page share filter state.
 */

const NS = 'filterprefs.';

type Listener = (snapshot: unknown) => void;

@Injectable({ providedIn: 'root' })
export class FilterPersistenceService {
  private doc = inject(DOCUMENT);

  private listeners = new Map<string, Set<Listener>>();
  private wired = false;

  read<T = unknown>(pageId: string, fallback: T | null = null): T | null {
    try {
      const raw = this.doc.defaultView?.localStorage.getItem(NS + pageId);
      if (!raw) return fallback;
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
  }

  write(pageId: string, snapshot: unknown): void {
    try {
      this.doc.defaultView?.localStorage.setItem(
        NS + pageId,
        JSON.stringify(snapshot),
      );
    } catch {
      /* QuotaExceeded — ignore */
    }
  }

  clear(pageId: string): void {
    try {
      this.doc.defaultView?.localStorage.removeItem(NS + pageId);
    } catch {
      /* ignore */
    }
  }

  subscribe(pageId: string, fn: Listener): () => void {
    this.wireStorageListener();
    let set = this.listeners.get(pageId);
    if (!set) {
      set = new Set();
      this.listeners.set(pageId, set);
    }
    set.add(fn);
    return () => {
      this.listeners.get(pageId)?.delete(fn);
    };
  }

  private wireStorageListener(): void {
    if (this.wired) return;
    this.wired = true;
    const w = this.doc.defaultView;
    if (!w) return;
    w.addEventListener('storage', (ev) => {
      if (!ev.key || !ev.key.startsWith(NS)) return;
      const pageId = ev.key.slice(NS.length);
      const set = this.listeners.get(pageId);
      if (!set || set.size === 0) return;
      let payload: unknown;
      try {
        payload = ev.newValue ? JSON.parse(ev.newValue) : null;
      } catch {
        payload = null;
      }
      for (const fn of set) {
        try {
          fn(payload);
        } catch {
          /* listener threw — don't let it break siblings */
        }
      }
    });
  }
}
