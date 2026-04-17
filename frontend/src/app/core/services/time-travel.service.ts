import { Injectable, computed, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';

/**
 * Phase MX3 / Gaps 345 + 346 — "Show me yesterday" + "What changed".
 *
 * Session-scoped time pointer that unlocks reading any page as of a
 * past snapshot. Components opt in by reading `service.asOf()` in
 * their HTTP calls and passing `?as_of=ISO` — the backend resolves
 * the closest historical snapshot.
 *
 * Also records the "last seen" timestamp per route so the Gap 346
 * "what changed" diff component can highlight deltas since the
 * operator's last visit.
 */

const STORAGE_AS_OF = 'timetravel.asof';
const STORAGE_LAST_SEEN = 'timetravel.lastseen.v1';

@Injectable({ providedIn: 'root' })
export class TimeTravelService {
  private doc = inject(DOCUMENT);

  private readonly _asOf = signal<string | null>(this.readAsOf());
  readonly asOf = this._asOf.asReadonly();
  readonly active = computed(() => !!this._asOf());
  readonly bannerText = computed(() => {
    const v = this._asOf();
    if (!v) return '';
    return `Time-travel: showing state as of ${new Date(v).toLocaleString()}. Close to return to live.`;
  });

  setAsOf(iso: string | null): void {
    this._asOf.set(iso);
    try {
      if (iso) this.doc.defaultView?.localStorage.setItem(STORAGE_AS_OF, iso);
      else this.doc.defaultView?.localStorage.removeItem(STORAGE_AS_OF);
    } catch {
      /* private mode */
    }
  }

  // ── "What changed since last visit" ─────────────────────────────

  /** Returns the timestamp (ISO) of the user's previous visit to
   *  this route, then updates the stored value to now. Pages call
   *  this in ngOnInit and diff their data against the returned ts. */
  touchAndGetLastSeen(routeKey: string): string | null {
    const map = this.readLastSeenMap();
    const prev = map[routeKey] ?? null;
    map[routeKey] = new Date().toISOString();
    this.writeLastSeenMap(map);
    return prev;
  }

  clearLastSeen(routeKey: string): void {
    const map = this.readLastSeenMap();
    if (routeKey in map) {
      delete map[routeKey];
      this.writeLastSeenMap(map);
    }
  }

  private readAsOf(): string | null {
    try {
      return this.doc.defaultView?.localStorage.getItem(STORAGE_AS_OF) ?? null;
    } catch {
      return null;
    }
  }

  private readLastSeenMap(): Record<string, string> {
    try {
      const raw = this.doc.defaultView?.localStorage.getItem(STORAGE_LAST_SEEN);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, string>) : {};
    } catch {
      return {};
    }
  }

  private writeLastSeenMap(map: Record<string, string>): void {
    try {
      this.doc.defaultView?.localStorage.setItem(
        STORAGE_LAST_SEEN,
        JSON.stringify(map),
      );
    } catch {
      /* private mode */
    }
  }
}
