import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, NgZone, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { interval } from 'rxjs';

export type SessionTimeoutChoice = 'stay' | 'signout' | 'expired';

export interface SessionTimeoutWarningResult {
  choice: SessionTimeoutChoice;
}

export interface SessionTimeoutWarningData {
  /** Absolute clock time (ms since epoch) when the token will expire. */
  expiresAt: number;
  /** Full warning-window length in ms (used to draw the progress bar). */
  windowMs: number;
}

/**
 * Phase E2 / Gap 42 — Session-timeout warning dialog.
 *
 * Opened by SessionTimeoutService ~2 minutes before the long-lived token
 * expires. Shows a live countdown plus two actions:
 *
 *   - "Stay signed in" → closes with `choice: 'stay'`. The service then
 *     calls `auth.markTokenRefreshed()` to reset the countdown. The
 *     current page/form state is preserved — no route change.
 *   - "Sign out now" → closes with `choice: 'signout'`. Service calls
 *     `auth.logout()`.
 *
 * If the user does nothing, the dialog closes itself with
 * `choice: 'expired'` when the countdown hits zero — at that point the
 * next HTTP call will 401 and Gap 14's reauth dialog will take over.
 *
 * Design notes:
 *   - `disableClose: true` — the user must make a choice (clicking
 *     backdrop or pressing ESC does nothing). Matches Gap 14 reauth
 *     dialog behaviour for consistency.
 *   - OnPush + ChangeDetectorRef.markForCheck() on each tick — the
 *     countdown updates once per second without bombing CD across the
 *     rest of the app.
 *   - Progress bar animates from 100% → 0% over the 2-minute window so
 *     the visual urgency matches the numeric countdown.
 */
@Component({
  selector: 'app-session-timeout-warning-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon aria-hidden="true" class="title-icon">schedule</mat-icon>
      Still there?
    </h2>
    <mat-dialog-content>
      <p class="dialog-intro">
        Your session will expire in
        <strong>{{ remainingLabel }}</strong>.
        Click <strong>Stay signed in</strong> to keep working. Your current
        page will not be lost.
      </p>

      <mat-progress-bar
        mode="determinate"
        [value]="progressPercent"
        class="countdown-bar"
        [class.countdown-bar-urgent]="remainingMs < 30_000"
      />
      <div class="countdown-meta" aria-live="polite">
        {{ remainingLabel }} remaining
      </div>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button
              type="button"
              (click)="onSignOut()">
        Sign out now
      </button>
      <button mat-raised-button
              color="primary"
              type="button"
              cdkFocusInitial
              (click)="onStay()">
        <mat-icon>refresh</mat-icon>
        Stay signed in
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon {
      vertical-align: middle;
      margin-right: 4px;
      color: var(--color-warning);
    }
    .dialog-intro {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 16px;
      line-height: 1.5;
    }
    .countdown-bar {
      border-radius: 4px;
      overflow: hidden;
      height: 6px;
    }
    .countdown-bar-urgent ::ng-deep .mdc-linear-progress__bar-inner {
      /* Switch to error red when under 30s. */
      border-color: var(--color-error) !important;
    }
    .countdown-meta {
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-top: 8px;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    mat-dialog-actions mat-icon {
      margin-right: 4px;
    }
  `],
})
export class SessionTimeoutWarningDialogComponent implements OnInit {
  private readonly dialogRef = inject(
    MatDialogRef<SessionTimeoutWarningDialogComponent, SessionTimeoutWarningResult>
  );
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);
  private readonly ngZone = inject(NgZone);
  private readonly data = inject<SessionTimeoutWarningData>(MAT_DIALOG_DATA);

  private readonly expiresAt = this.data.expiresAt;
  private readonly windowMs = this.data.windowMs;

  remainingMs = Math.max(0, this.expiresAt - Date.now());

  get remainingLabel(): string {
    const total = Math.max(0, Math.ceil(this.remainingMs / 1000));
    const mm = Math.floor(total / 60);
    const ss = total % 60;
    return `${mm}:${ss.toString().padStart(2, '0')}`;
  }

  get progressPercent(): number {
    // windowMs is the full warning window (e.g. 120000 for 2 min).
    // At start = 100%, at 0 ms remaining = 0%.
    return Math.max(0, Math.min(100, (this.remainingMs / this.windowMs) * 100));
  }

  ngOnInit(): void {
    this.tick();
    // Run the 1-second countdown OUTSIDE the Angular zone so each tick
    // does not schedule global change detection. OnPush dialog: we
    // explicitly `markForCheck` inside `tick()` to paint the new value.
    // `dialogRef.close()` must run INSIDE the zone so the post-close
    // logic (router navigation, subscriptions on afterClosed) fires
    // the expected change-detection pass.
    this.ngZone.runOutsideAngular(() => {
      interval(1000)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.tick());
    });
  }

  private tick(): void {
    this.remainingMs = Math.max(0, this.expiresAt - Date.now());
    if (this.remainingMs <= 0) {
      this.ngZone.run(() => this.dialogRef.close({ choice: 'expired' }));
      return;
    }
    this.cdr.markForCheck();
  }

  onStay(): void {
    this.dialogRef.close({ choice: 'stay' });
  }

  onSignOut(): void {
    this.dialogRef.close({ choice: 'signout' });
  }
}
