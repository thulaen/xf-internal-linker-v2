import { Injectable, NgZone, computed, inject, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase E2 / Gap 52 — Connection-aware loading.
 *
 * Reads `navigator.connection` (Network Information API) to answer:
 *   "is the user on a slow or metered connection?"
 *
 * Components can either:
 *   - Subscribe to `connection$` for reactive updates.
 *   - Call `shouldDeferHeavy()` for a one-shot read at init.
 *   - Read the `isSlow` / `saveData` signals directly in templates.
 *
 * Example (defer a heavy chart on slow connections):
 *
 *   constructor(private conn: ConnectionService) {}
 *
 *   get showHeavyChart(): boolean {
 *     return !this.conn.shouldDeferHeavy();
 *   }
 *
 * Example (template with signals):
 *
 *   @if (conn.isSlow()) {
 *     <button (click)="loadChart()">Load chart (may be slow)</button>
 *   } @else {
 *     <app-heavy-chart />
 *   }
 *
 * Firefox and Safari do not implement Network Information API as of
 * 2026. In those browsers we return conservative "assume fast" values
 * so users aren't wrongly penalised.
 */

type EffectiveType = '4g' | '3g' | '2g' | 'slow-2g' | 'unknown';

interface ConnectionLike {
  effectiveType?: EffectiveType;
  saveData?: boolean;
  downlink?: number;      // Mbps
  rtt?: number;           // ms
  addEventListener?: (type: 'change', listener: () => void) => void;
  removeEventListener?: (type: 'change', listener: () => void) => void;
}

export interface ConnectionInfo {
  effectiveType: EffectiveType;
  saveData: boolean;
  downlink: number | null;
  rtt: number | null;
}

@Injectable({ providedIn: 'root' })
export class ConnectionService {
  private readonly zone = inject(NgZone);

  private readonly state = signal<ConnectionInfo>(this.readConnection());

  /** Reactive read for templates / effects. */
  readonly info = this.state.asReadonly();

  /** `true` when the connection is slow enough that heavy content should be
   *  deferred or user-gated. 2g / slow-2g qualifies; `saveData` also forces
   *  this regardless of effective type (the user asked for less data). */
  readonly isSlow = computed(() => {
    const s = this.state();
    if (s.saveData) return true;
    return s.effectiveType === '2g' || s.effectiveType === 'slow-2g';
  });

  /** `true` if the user has explicitly enabled Data Saver. */
  readonly saveData = computed(() => this.state().saveData);

  /** Observable form for code that prefers RxJS. */
  readonly info$ = toObservable(this.state);

  constructor() {
    const conn = this.getConnection();
    if (!conn?.addEventListener) return;

    // Listen outside the zone — change events are rare but we don't want
    // to thrash CD on metered-network toggles.
    this.zone.runOutsideAngular(() => {
      conn.addEventListener!('change', () => {
        this.zone.run(() => this.state.set(this.readConnection()));
      });
    });
  }

  /** One-shot helper for imperative code. */
  shouldDeferHeavy(): boolean {
    return this.isSlow();
  }

  // ── internals ──────────────────────────────────────────────────────

  private getConnection(): ConnectionLike | null {
    if (typeof navigator === 'undefined') return null;
    const n = navigator as Navigator & {
      connection?: ConnectionLike;
      mozConnection?: ConnectionLike;
      webkitConnection?: ConnectionLike;
    };
    return n.connection ?? n.mozConnection ?? n.webkitConnection ?? null;
  }

  private readConnection(): ConnectionInfo {
    const c = this.getConnection();
    if (!c) {
      // Firefox / Safari fallback — assume "fast" to avoid wrongly
      // degrading the experience.
      return {
        effectiveType: 'unknown',
        saveData: false,
        downlink: null,
        rtt: null,
      };
    }
    return {
      effectiveType: (c.effectiveType as EffectiveType) ?? 'unknown',
      saveData: !!c.saveData,
      downlink: typeof c.downlink === 'number' ? c.downlink : null,
      rtt: typeof c.rtt === 'number' ? c.rtt : null,
    };
  }
}
