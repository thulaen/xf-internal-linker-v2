import { Injectable, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D1 / Gap 58 — Explain-Mode service.
 *
 * A global toggle that, when ON, reveals inline "what is this?"
 * annotations on every widget that opts in via the
 * `<app-explain-badge>` component. Persisted in localStorage so the
 * preference survives reloads.
 *
 * Distinct from Tutorial Mode (Gap 55):
 *   - Tutorial Mode shows a persistent, per-card dismissable callout
 *     ABOVE each widget — it teaches the widget's purpose.
 *   - Explain Mode adds a small info icon IN each widget that expands
 *     on hover/click to a plain-English definition of the thing being
 *     shown (e.g., the metric's definition, the chart's Y-axis meaning).
 *
 * A user can have both on at once without conflict. Most noobs will
 * leave Tutorial Mode on for a week and Explain Mode on indefinitely.
 */

const KEY = 'xfil_explain_mode';

@Injectable({ providedIn: 'root' })
export class ExplainModeService {
  private readonly enabledSignal = signal<boolean>(this.read());

  readonly enabled = this.enabledSignal.asReadonly();
  readonly enabled$ = toObservable(this.enabledSignal);

  toggle(): void {
    this.setEnabled(!this.enabledSignal());
  }

  setEnabled(next: boolean): void {
    this.enabledSignal.set(next);
    try {
      localStorage.setItem(KEY, next ? '1' : '0');
    } catch {
      // Private-mode — in-memory only is fine.
    }
  }

  private read(): boolean {
    try {
      return localStorage.getItem(KEY) === '1';
    } catch {
      return false;
    }
  }
}
