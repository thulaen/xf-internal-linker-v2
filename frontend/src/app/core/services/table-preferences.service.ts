import { Injectable } from '@angular/core';

/**
 * Phase E1 / Gap 36 — Table-preferences persistence.
 *
 * Stores per-table user preferences in localStorage so that column
 * visibility, sort direction, and page size survive page reloads and
 * browser restarts.
 *
 * Each table is identified by a unique string key (its `tableId`).
 * Preferences are stored under the key `tbl_prefs_<tableId>` to avoid
 * collisions with other localStorage keys.
 *
 * Usage:
 *
 *   private prefs = inject(TablePreferencesService);
 *
 *   // Save when the user changes something:
 *   onSortChange(sort: Sort) {
 *     this.prefs.save('alerts', { sortActive: sort.active, sortDir: sort.direction });
 *   }
 *
 *   // Restore on init:
 *   ngOnInit() {
 *     const saved = this.prefs.load<AlertPrefs>('alerts');
 *     if (saved) { this.applyPrefs(saved); }
 *   }
 *
 * The prefs object is merged with any existing prefs for that tableId so
 * you can save partial updates (e.g. just the page size).
 */
@Injectable({ providedIn: 'root' })
export class TablePreferencesService {
  private readonly prefix = 'tbl_prefs_';

  /**
   * Load saved preferences for a table. Returns null if nothing is stored
   * or if the stored JSON is corrupt.
   */
  load<T extends Record<string, unknown>>(tableId: string): T | null {
    try {
      const raw = localStorage.getItem(this.key(tableId));
      if (!raw) return null;
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  /**
   * Save (merge) preferences for a table.
   * Existing keys not present in `prefs` are preserved.
   */
  save<T extends Record<string, unknown>>(tableId: string, prefs: Partial<T>): void {
    try {
      const existing = this.load<T>(tableId) ?? ({} as T);
      const merged = { ...existing, ...prefs };
      localStorage.setItem(this.key(tableId), JSON.stringify(merged));
    } catch {
      /* localStorage may be full or unavailable in private mode — fail silently */
    }
  }

  /** Clear all saved preferences for a table. */
  clear(tableId: string): void {
    try {
      localStorage.removeItem(this.key(tableId));
    } catch {
      /* ignore */
    }
  }

  /** Clear ALL table preferences stored by this service. */
  clearAll(): void {
    try {
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k?.startsWith(this.prefix)) keysToRemove.push(k);
      }
      keysToRemove.forEach((k) => localStorage.removeItem(k));
    } catch {
      /* ignore */
    }
  }

  private key(tableId: string): string {
    return `${this.prefix}${tableId}`;
  }
}
