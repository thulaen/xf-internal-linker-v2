import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, NgZone, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MAT_SNACK_BAR_DATA, MatSnackBarRef } from '@angular/material/snack-bar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { interval } from 'rxjs';

export interface RateLimitSnackbarData {
  /** Seconds the server asked us to wait (from Retry-After header). */
  seconds: number;
}

/**
 * Phase E2 / Gap 43 — 429 Retry-After countdown snackbar.
 *
 * Replaces the single-shot "Too many requests" toast with a live
 * countdown. The user sees exactly when they can retry. Self-dismisses
 * at zero. Works with both header formats — an integer "seconds" value
 * or an HTTP-date (parsing happens upstream in the interceptor; we only
 * receive the already-resolved seconds here).
 *
 * KISS reasoning:
 *   - OnPush + `markForCheck()` once per second = 60 frames over the
 *     typical 60-second window. Cheap.
 *   - Keeps the raw snackbar chrome — no custom positioning, no new
 *     overlay. It looks and behaves like every other snackbar.
 *   - Dismiss button is wired to the standard snackbar action slot so
 *     screen-reader users can cancel it early.
 */
@Component({
  selector: 'app-rate-limit-snackbar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule],
  template: `
    <div class="rl-snack" role="status" aria-live="polite">
      <mat-icon class="rl-icon" aria-hidden="true">schedule</mat-icon>
      <span class="rl-text">
        Too many requests — try again in
        <strong>{{ remainingLabel }}</strong>.
      </span>
      <button mat-button class="rl-dismiss" (click)="snackRef.dismiss()">
        Dismiss
      </button>
    </div>
  `,
  styles: [`
    :host {
      display: block;
      color: var(--color-text-primary);
    }
    .rl-snack {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .rl-icon {
      color: var(--color-warning);
      font-size: 20px;
      width: 20px;
      height: 20px;
    }
    .rl-text {
      flex: 1;
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }
    .rl-dismiss {
      flex-shrink: 0;
    }
  `],
})
export class RateLimitSnackbarComponent implements OnInit {
  readonly snackRef = inject<MatSnackBarRef<RateLimitSnackbarComponent>>(MatSnackBarRef);
  private readonly data = inject<RateLimitSnackbarData>(MAT_SNACK_BAR_DATA);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);
  private readonly ngZone = inject(NgZone);

  remainingSeconds = Math.max(0, Math.floor(this.data.seconds));

  get remainingLabel(): string {
    const s = this.remainingSeconds;
    if (s <= 0) return 'now';
    if (s === 1) return '1 second';
    if (s < 60) return `${s} seconds`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    if (m === 1 && rem === 0) return '1 minute';
    if (rem === 0) return `${m} minutes`;
    return `${m}m ${rem.toString().padStart(2, '0')}s`;
  }

  ngOnInit(): void {
    if (this.remainingSeconds <= 0) {
      this.snackRef.dismiss();
      return;
    }
    // Run the 1-second countdown OUTSIDE the Angular zone so each tick
    // does not schedule global change detection. The snackbar is OnPush,
    // so we explicitly `markForCheck` to paint the new value. `dismiss()`
    // stays on the zone path (it's an event-driven signal, not a tick).
    // See docs/PERFORMANCE.md §13.
    this.ngZone.runOutsideAngular(() => {
      interval(1000)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => {
          this.remainingSeconds = Math.max(0, this.remainingSeconds - 1);
          if (this.remainingSeconds <= 0) {
            this.ngZone.run(() => this.snackRef.dismiss());
          } else {
            this.cdr.markForCheck();
          }
        });
    });
  }
}
