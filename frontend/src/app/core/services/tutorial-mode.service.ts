import { Injectable, computed, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D1 / Gap 55 — Tutorial Mode service.
 *
 * Persists a global "tutorial mode" toggle in localStorage. When ON:
 *   - Every dashboard card shows a small callout explaining what it does.
 *   - The noob-friendly narrative strings are verbose.
 *
 * Per-card dismissal is tracked separately: the user can hide a specific
 * callout without turning the whole mode off. Re-enabling tutorial mode
 * resets the per-card dismissals so the user sees everything again.
 *
 * Why a service, not a signal on the component: tutorial mode is global
 * — the sidenav, toolbar, and any future page can all read it. A service
 * also gives us observable form for components that prefer RxJS.
 */

const MODE_KEY = 'xfil_tutorial_mode';
const DISMISS_KEY_PREFIX = 'xfil_tutorial_dismissed.';

@Injectable({ providedIn: 'root' })
export class TutorialModeService {
  private readonly enabledSignal = signal<boolean>(this.readMode());

  /** Reactive read — reactive consumers use `signal()` form. */
  readonly enabled = this.enabledSignal.asReadonly();

  /** Observable form for RxJS-heavy callers. */
  readonly enabled$ = toObservable(this.enabledSignal);

  /** Dismissal snapshot — reflects localStorage but is NOT reactive per
   *  card. Individual callout components re-read on init; that's fine —
   *  dismissals are a one-way ratchet during a session. */
  private readonly dismissalsSignal = signal<Set<string>>(this.readDismissed());

  /** Signal of whether a specific card id is currently dismissed. */
  isDismissed(cardId: string) {
    return computed(() => this.dismissalsSignal().has(cardId));
  }

  /** Flip tutorial mode. When turning ON, clear per-card dismissals so
   *  the user sees everything again — otherwise toggling off and on
   *  would leave callouts silently hidden. */
  toggle(): void {
    const next = !this.enabledSignal();
    this.setEnabled(next);
  }

  setEnabled(next: boolean): void {
    this.enabledSignal.set(next);
    try {
      localStorage.setItem(MODE_KEY, next ? '1' : '0');
      if (next) {
        // Fresh slate.
        this.clearAllDismissals();
      }
    } catch {
      // Private mode — state still lives in memory for this session.
    }
  }

  /** Dismiss the callout for a specific card id. Idempotent. */
  dismiss(cardId: string): void {
    const next = new Set(this.dismissalsSignal());
    if (next.has(cardId)) return;
    next.add(cardId);
    this.dismissalsSignal.set(next);
    try {
      localStorage.setItem(DISMISS_KEY_PREFIX + cardId, '1');
    } catch {
      // Private mode — in-memory only is fine.
    }
  }

  /** Phase GB / Gap 149 — Preference-Center "Show all hints again" button.
   *  Clears every remembered per-card dismissal without touching the
   *  master enabled flag, so the user can re-expose hints without
   *  toggling tutorial mode off and back on. */
  resetDismissals(): void {
    this.clearAllDismissals();
  }

  private clearAllDismissals(): void {
    this.dismissalsSignal.set(new Set());
    try {
      // Enumerate keys directly; there may be dozens.
      const toRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith(DISMISS_KEY_PREFIX)) toRemove.push(k);
      }
      for (const k of toRemove) localStorage.removeItem(k);
    } catch {
      // No-op.
    }
  }

  // ── initial-state helpers ──────────────────────────────────────────

  private readMode(): boolean {
    try {
      return localStorage.getItem(MODE_KEY) === '1';
    } catch {
      return false;
    }
  }

  private readDismissed(): Set<string> {
    const out = new Set<string>();
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith(DISMISS_KEY_PREFIX)) {
          out.add(k.slice(DISMISS_KEY_PREFIX.length));
        }
      }
    } catch {
      // Ignore.
    }
    return out;
  }
}
