import { Injectable, signal } from '@angular/core';

/**
 * Phase D3 / Gap 169 — Save-current-layout-as-default service.
 *
 * Persists which dashboard cards the user has hidden / pinned via the
 * existing card-prefs UI (toggleable in the future), and lets them
 * reset to the default layout. The actual list of hidden card ids
 * lives in localStorage; components opt in by reading
 * `isHidden(cardId)` and rendering nothing when it's true.
 *
 * Distinct from Calm Mode (Gap 167, which hides ALL non-essential
 * cards based on a flag): this is per-card user choice.
 */

const KEY = 'xfil_dashboard_hidden_cards';

@Injectable({ providedIn: 'root' })
export class DashboardLayoutService {
  private readonly _hidden = signal<ReadonlySet<string>>(this.read());

  readonly hidden = this._hidden.asReadonly();

  isHidden(cardId: string): boolean {
    return this._hidden().has(cardId);
  }

  hide(cardId: string): void {
    const next = new Set(this._hidden());
    if (next.has(cardId)) return;
    next.add(cardId);
    this._hidden.set(next);
    this.persist(next);
  }

  show(cardId: string): void {
    const next = new Set(this._hidden());
    if (!next.has(cardId)) return;
    next.delete(cardId);
    this._hidden.set(next);
    this.persist(next);
  }

  /** Snapshot the current hidden set as the user's "default" — same
   *  thing the auto-persistence already does, but exposed as an
   *  explicit user gesture for the "Save as default" button. */
  saveAsDefault(): void {
    this.persist(this._hidden());
  }

  /** Wipe the hidden set so every card renders again. */
  resetToFactory(): void {
    this._hidden.set(new Set());
    try {
      localStorage.removeItem(KEY);
    } catch {
      // No-op.
    }
  }

  // ── helpers ────────────────────────────────────────────────────────

  private read(): Set<string> {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return new Set();
      const arr = JSON.parse(raw) as string[];
      return new Set(Array.isArray(arr) ? arr : []);
    } catch {
      return new Set();
    }
  }

  private persist(set: ReadonlySet<string>): void {
    try {
      localStorage.setItem(KEY, JSON.stringify([...set]));
    } catch {
      // In-memory only.
    }
  }
}
