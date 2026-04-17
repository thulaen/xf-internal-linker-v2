import { Injectable, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';

/**
 * Phase NV / Gap 145 — Tab groups persistence.
 *
 * Tiny key-value store for the last-active tab index of any MatTabGroup
 * in the app. Keyed by a stable ID supplied by the caller (page slug
 * + a tab-group label, e.g. "settings.connections").
 *
 * Storage = localStorage so the value survives logout/login on the same
 * browser. Each entry is namespaced under `tabprefs.` to keep the
 * storage key set tidy and easy to clear.
 *
 * The service is intentionally framework-agnostic — the
 * `appPersistTab` directive is the consumer that wires it up to
 * MatTabGroup's `selectedIndexChange` output.
 */
@Injectable({ providedIn: 'root' })
export class TabPersistenceService {
  private doc = inject(DOCUMENT);
  private readonly NS = 'tabprefs.';

  /** Returns the last-saved index for `id`, or `fallback` (default 0) if nothing stored. */
  read(id: string, fallback = 0): number {
    try {
      const raw = this.doc.defaultView?.localStorage.getItem(this.key(id));
      if (raw === null || raw === undefined) return fallback;
      const n = Number.parseInt(raw, 10);
      return Number.isFinite(n) && n >= 0 ? n : fallback;
    } catch {
      return fallback;
    }
  }

  write(id: string, index: number): void {
    if (!Number.isFinite(index) || index < 0) return;
    try {
      this.doc.defaultView?.localStorage.setItem(this.key(id), String(index));
    } catch {
      /* swallow QuotaExceeded etc. */
    }
  }

  clear(id: string): void {
    try {
      this.doc.defaultView?.localStorage.removeItem(this.key(id));
    } catch {
      /* ignore */
    }
  }

  /** Wipe every persisted tab — used by the user-pref-center "Reset prefs" button. */
  clearAll(): void {
    try {
      const ls = this.doc.defaultView?.localStorage;
      if (!ls) return;
      const toRemove: string[] = [];
      for (let i = 0; i < ls.length; i++) {
        const k = ls.key(i);
        if (k && k.startsWith(this.NS)) toRemove.push(k);
      }
      for (const k of toRemove) ls.removeItem(k);
    } catch {
      /* ignore */
    }
  }

  private key(id: string): string {
    return this.NS + id;
  }
}
