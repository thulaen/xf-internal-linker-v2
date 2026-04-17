import { Injectable } from '@angular/core';

/**
 * Phase F1 / Gap 87 — IndexedDB-backed offline cache.
 *
 * Caches small JSON payloads (dashboard summary, last-known suggestion
 * counts, mission brief) so that when the user opens the app while
 * offline, the dashboard isn't blank — it shows the most recent
 * snapshot with a "you're offline" banner (already exists, see
 * `offline-banner` Gap 11).
 *
 * Why IndexedDB and not localStorage:
 *   - localStorage is synchronous and string-only; large JSON payloads
 *     stringified/parsed on the main thread cause INP regressions.
 *   - IndexedDB is async, structured-clone-friendly, and has a much
 *     larger quota (50MB+ on most browsers).
 *
 * Single object store keyed by string. Each entry stamps `cachedAt`
 * so consumers can decide what counts as too stale to show.
 *
 * Usage:
 *
 *   await offline.put('dashboard', dashboardData);
 *   const cached = await offline.get<DashboardData>('dashboard');
 *   if (cached && Date.now() - cached.cachedAt < 24*60*60*1000) {
 *     // render cached snapshot while we wait for live data
 *   }
 */

const DB_NAME = 'xfil_offline';
const DB_VERSION = 1;
const STORE = 'cache';

export interface CachedEntry<T> {
  value: T;
  cachedAt: number;
}

@Injectable({ providedIn: 'root' })
export class OfflineStoreService {
  private dbPromise: Promise<IDBDatabase | null> | null = null;

  /** Read a cached entry. Returns null when missing, when IndexedDB
   *  isn't available, or when the value can't be deserialised. */
  async get<T = unknown>(key: string): Promise<CachedEntry<T> | null> {
    const db = await this.openDb();
    if (!db) return null;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, 'readonly');
        const store = tx.objectStore(STORE);
        const req = store.get(key);
        req.onsuccess = () => {
          const v = req.result as CachedEntry<T> | undefined;
          resolve(v ?? null);
        };
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  /** Write a value. Stamps `cachedAt` automatically. */
  async put<T = unknown>(key: string, value: T): Promise<void> {
    const db = await this.openDb();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, 'readwrite');
        const store = tx.objectStore(STORE);
        const entry: CachedEntry<T> = { value, cachedAt: Date.now() };
        const req = store.put(entry, key);
        req.onsuccess = () => resolve();
        req.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  /** Delete a single key. */
  async remove(key: string): Promise<void> {
    const db = await this.openDb();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  /** Wipe the whole cache — wired to "One-Button Reset" or sign-out. */
  async clear(): Promise<void> {
    const db = await this.openDb();
    if (!db) return;
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  // ── internals ──────────────────────────────────────────────────────

  private openDb(): Promise<IDBDatabase | null> {
    if (this.dbPromise) return this.dbPromise;
    if (typeof indexedDB === 'undefined') {
      this.dbPromise = Promise.resolve(null);
      return this.dbPromise;
    }
    this.dbPromise = new Promise<IDBDatabase | null>((resolve) => {
      try {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains(STORE)) {
            db.createObjectStore(STORE);
          }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
        req.onblocked = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
    return this.dbPromise;
  }
}
