import { Injectable, computed, signal } from '@angular/core';

/**
 * Phase GK1 / Gap 213 — Toast history panel.
 *
 * Many snackbars / toasts fly by before an operator can read them.
 * This service keeps the last 50 in memory (not persisted — session
 * scope is the right fit: you came back, you didn't miss yesterday's
 * toasts). The app-shell's "Toast history" drawer renders them.
 *
 * Call pattern:
 *   - Every `snack.open(...)` wrapper in the app pushes via
 *     `toastHistory.record(message, severity)`.
 *   - The drawer reads `entries()` and allows a user-initiated clear.
 */

export type ToastSeverity = 'info' | 'success' | 'warning' | 'error';

export interface ToastRecord {
  id: string;
  message: string;
  severity: ToastSeverity;
  at: number;
}

const MAX = 50;

@Injectable({ providedIn: 'root' })
export class ToastHistoryService {
  private readonly _entries = signal<ToastRecord[]>([]);

  /** Newest-first. */
  readonly entries = computed(() => this._entries());

  record(
    message: string,
    severity: ToastSeverity = 'info',
  ): ToastRecord {
    const entry: ToastRecord = {
      id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      message,
      severity,
      at: Date.now(),
    };
    const next = [entry, ...this._entries()].slice(0, MAX);
    this._entries.set(next);
    return entry;
  }

  clear(): void {
    this._entries.set([]);
  }
}
