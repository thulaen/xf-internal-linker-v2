import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar } from '@angular/material/snack-bar';

import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';

/**
 * Phase D3 / Gap 168 — Red top-right Emergency Stop kill-switch.
 *
 * Distinct from the toolbar's "pause everything" master toggle (Plan
 * Item 28) — pause is a graceful "stop at next checkpoint" affordance.
 * Emergency Stop is the panic button that:
 *   1. Sends master_pause=true (stops new work).
 *   2. Calls the queue-clear endpoint to abandon queued tasks.
 *
 * Wrapped in a typed-string confirm dialog so an accidental click can't
 * trigger it. Disabled while a previous call is in flight.
 */
@Component({
  selector: 'app-emergency-stop',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
  ],
  template: `
    <button
      mat-flat-button
      type="button"
      class="es-btn"
      [disabled]="busy()"
      matTooltip="Stop all workers immediately and clear the queue"
      aria-label="Emergency stop"
      (click)="onClick()"
    >
      <mat-icon>emergency</mat-icon>
      Emergency stop
    </button>
  `,
  styles: [`
    .es-btn {
      background: var(--color-error, #d93025) !important;
      color: #ffffff !important;
      font-weight: 500;
      letter-spacing: 0.4px;
    }
    .es-btn:hover:not(:disabled) {
      background: var(--color-error-dark, #b3261e) !important;
    }
    .es-btn:disabled {
      opacity: 0.5;
    }
  `],
})
export class EmergencyStopComponent {
  private readonly http = inject(HttpClient);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);
  private readonly confirmSvc = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  readonly busy = signal(false);

  async onClick(): Promise<void> {
    if (this.busy()) return;
    // Two-stage confirmation:
    //   Stage 1 — standard danger ConfirmDialog.
    //   Stage 2 — native prompt requiring the literal string "STOP".
    const ok = await this.confirmSvc.ask({
      title: 'Emergency stop?',
      message:
        'Pauses every worker AND abandons everything in the queue. ' +
        'In-flight tasks will be killed at the next checkpoint.',
      confirmLabel: 'Continue…',
      cancelLabel: 'Cancel',
      danger: true,
      icon: 'emergency',
    });
    if (!ok) return;
    const typed = window.prompt('Type STOP to confirm emergency stop:') ?? '';
    if (typed.trim().toUpperCase() !== 'STOP') {
      this.snack.open('Cancelled.', 'OK', { duration: 2500 });
      return;
    }

    this.busy.set(true);
    // Step 1 — engage master pause. Reuses the existing endpoint
    // (POST /api/settings/master-pause/ { paused: true }).
    this.http
      .post('/api/settings/master-pause/', { paused: true })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.purgeQueue(),
        error: () => {
          this.busy.set(false);
          this.snack.open(
            'Emergency stop failed at master pause — try the manual pause button.',
            'Dismiss',
            { duration: 5000 },
          );
        },
      });
  }

  /** Best-effort queue purge. If the endpoint doesn't exist we still
   *  win — master pause is the more important effect. */
  private purgeQueue(): void {
    this.http
      .post('/api/jobs/queue/abort-all/', {})
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.snack.open(
            'Emergency stop engaged. Workers paused and queue cleared.',
            'OK',
            { duration: 6000 },
          );
        },
        error: () => {
          // Master pause succeeded; queue purge endpoint may not exist
          // yet. Tell the user what happened so they're not surprised.
          this.busy.set(false);
          this.snack.open(
            'Master pause engaged. Queue could not be cleared automatically — open Jobs to abandon individually.',
            'Dismiss',
            { duration: 7000 },
          );
        },
      });
  }
}
