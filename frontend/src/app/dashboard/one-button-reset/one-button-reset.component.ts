import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';

import { DashboardService } from '../dashboard.service';
import { RealtimeService } from '../../core/services/realtime.service';

/**
 * Phase D2 / Gap 68 — "Something feels weird" One-Button Reset.
 *
 * A single button that does the safest possible "everything is wrong,
 * try again" sequence:
 *   1. Invalidate the dashboard SWR cache.
 *   2. Force a fresh dashboard refresh.
 *   3. Reconnect the WebSocket so any stuck subscription is rebuilt.
 *
 * Notably DOES NOT:
 *   - Log out the user.
 *   - Clear localStorage (preserves preferences, draft state).
 *   - Delete server-side data.
 *
 * The point is to give noobs a one-click escape from "I think the
 * page is showing stale numbers." A power user with the same problem
 * would hit F5; this gives noobs a labeled equivalent that doesn't
 * actually nuke their unsaved work.
 */
@Component({
  selector: 'app-one-button-reset',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <mat-card class="obr-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="obr-avatar">restart_alt</mat-icon>
        <mat-card-title>Something feels weird?</mat-card-title>
        <mat-card-subtitle>One-click safe reset of the dashboard view</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <p class="obr-body">
          Refreshes the dashboard data, reconnects the live updates feed,
          and clears the cached snapshot. Doesn't touch your settings or
          unsaved work.
        </p>
        @if (lastResetAt()) {
          <p class="obr-meta">
            <mat-icon class="obr-meta-icon">check_circle</mat-icon>
            Last reset {{ lastResetLabel() }}.
          </p>
        }
      </mat-card-content>
      <mat-card-actions>
        <button
          mat-flat-button
          color="primary"
          type="button"
          [disabled]="busy()"
          (click)="onReset()"
        >
          @if (busy()) {
            <mat-spinner diameter="18" class="obr-spinner" />
          } @else {
            <mat-icon>refresh</mat-icon>
          }
          Reset the view
        </button>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    .obr-card { height: 100%; }
    .obr-avatar {
      background: var(--color-warning, #f9ab00);
      color: #ffffff;
    }
    .obr-body {
      margin: 0 0 12px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--color-text-secondary);
    }
    .obr-meta {
      display: flex;
      align-items: center;
      gap: 4px;
      margin: 0;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .obr-meta-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
      color: var(--color-success, #1e8e3e);
    }
    .obr-spinner {
      display: inline-block;
      margin-right: 8px;
    }
  `],
})
export class OneButtonResetComponent {
  private readonly dash = inject(DashboardService);
  private readonly realtime = inject(RealtimeService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly busy = signal(false);
  readonly lastResetAt = signal<number | null>(null);

  onReset(): void {
    if (this.busy()) return;
    this.busy.set(true);

    // Step 1 — flush the dashboard SWR cache so the next get() forces fresh.
    this.dash.invalidate();

    // Step 2 — kick a fresh fetch.
    this.dash
      .refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // Step 3 — bounce the websocket via the public force-reconnect
          // hook. The exponential backoff inside RealtimeService takes
          // over from there. Wrapped in try/catch so a missing method on
          // a future refactor doesn't blow up the user-facing snackbar.
          try {
            this.realtime.reconnectNow();
          } catch {
            // Best-effort.
          }
          this.busy.set(false);
          this.lastResetAt.set(Date.now());
          this.snack.open('Dashboard view reset.', 'OK', { duration: 3000 });
        },
        error: () => {
          this.busy.set(false);
          this.snack.open('Reset failed — check your connection.', 'Dismiss', {
            duration: 5000,
          });
        },
      });
  }

  lastResetLabel(): string {
    const t = this.lastResetAt();
    if (!t) return '';
    const secs = Math.floor((Date.now() - t) / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    return `${hours}h ago`;
  }
}
