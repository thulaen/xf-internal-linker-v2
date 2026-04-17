/**
 * ToastService — thin wrapper around MatSnackBar for alert-driven toasts.
 *
 * Only shows toasts for alerts at or above the configured severity threshold.
 * The error.interceptor continues to use MatSnackBar directly for HTTP errors.
 *
 * Phase E1 / Gap 31 — also exposes `showUndo()` for reversible actions.
 */

import { Injectable, NgZone, inject } from '@angular/core';
import { MatSnackBar, MatSnackBarConfig } from '@angular/material/snack-bar';
import { OperatorAlert } from './notification.service';

const SEVERITY_RANK: Record<string, number> = {
  info: 0,
  success: 1,
  warning: 2,
  error: 3,
  urgent: 4,
};

const DURATION_MS: Record<string, number> = {
  info: 4000,
  success: 4000,
  warning: 6000,
  error: 8000,
  urgent: 10000,
};

const PANEL_CLASS: Record<string, string> = {
  info: 'toast-info',
  success: 'toast-success',
  warning: 'toast-warning',
  error: 'toast-error',
  urgent: 'toast-urgent',
};

@Injectable({ providedIn: 'root' })
export class ToastService {
  private snackBar = inject(MatSnackBar);
  private zone = inject(NgZone);

  /**
   * Show a toast for an OperatorAlert if its severity meets the threshold.
   * minSeverity comes from the user's notification preferences.
   */
  showForAlert(alert: OperatorAlert, minSeverity = 'warning'): void {
    const alertRank = SEVERITY_RANK[alert.severity] ?? 0;
    const minRank = SEVERITY_RANK[minSeverity] ?? 2;
    if (alertRank < minRank) return;

    const config: MatSnackBarConfig = {
      duration: DURATION_MS[alert.severity] ?? 5000,
      panelClass: [PANEL_CLASS[alert.severity] ?? 'toast-info'],
      horizontalPosition: 'end',
      verticalPosition: 'bottom',
    };

    const action = alert.related_route ? 'Go' : 'Dismiss';
    const ref = this.snackBar.open(alert.title, action, config);

    if (alert.related_route) {
      ref.onAction().subscribe(() => {
        window.location.assign(alert.related_route);
      });
    }
  }

  /** Show a plain text message — used by existing HTTP error handling. */
  show(message: string, action = 'Dismiss', duration = 5000): void {
    this.snackBar.open(message, action, { duration, horizontalPosition: 'end' });
  }

  /**
   * Phase E1 / Gap 31 — Show a reversible-action snackbar with an "Undo"
   * action button. The caller supplies the function that reverts the change.
   *
   * If the user clicks "Undo" within the window the `undoFn` is called.
   * If the user dismisses or the timer expires, nothing is called.
   *
   * @param message   e.g. "Alert rule deleted"
   * @param undoFn    Called only if the user clicks Undo — should revert the
   *                  change. May return a Promise; errors are silently swallowed
   *                  (the snackbar is already gone by then).
   * @param durationMs Visible duration before auto-dismiss. Default 8 000 ms.
   */
  showUndo(
    message: string,
    undoFn: () => void | Promise<void>,
    durationMs = 8000,
  ): void {
    // Run inside Angular's zone so change detection fires after undo.
    this.zone.run(() => {
      const ref = this.snackBar.open(message, 'Undo', {
        duration: durationMs,
        horizontalPosition: 'end',
        verticalPosition: 'bottom',
        panelClass: ['toast-undo'],
      });

      ref.onAction().subscribe(() => {
        try {
          const result = undoFn();
          if (result instanceof Promise) {
            result.catch(() => { /* swallow — user already dismissed */ });
          }
        } catch {
          /* swallow — snackbar is gone, nothing to show */
        }
      });
    });
  }
}
