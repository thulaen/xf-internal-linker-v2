/**
 * ScheduledUpdatesComponent — the `/scheduled-updates` dashboard tab.
 *
 * Layout (mat-tab-group with four children):
 *   1. Alerts      — deduped active missed/failed/stalled rows, ack ✕.
 *   2. Running     — current in-flight job + progress bar + pause/cancel.
 *   3. Schedule    — missed / upcoming / all jobs with "Run Now" buttons.
 *   4. History     — last ~20 runs per job with duration + status.
 *
 * This slice (PR-B.7) lands the skeleton — the shell, route, nav wiring,
 * data subscriptions, and tab scaffolding. The individual tab cards get
 * their detail polish in PR-B.8 and PR-B.9.
 */

import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnDestroy,
  OnInit,
  inject,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { HttpErrorResponse } from '@angular/common/http';

import {
  JobAlert,
  ScheduledJob,
  ScheduledUpdatesService,
  WindowStatus,
} from './scheduled-updates.service';

@Component({
  selector: 'app-scheduled-updates',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    MatBadgeModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTabsModule,
    MatTooltipModule,
  ],
  templateUrl: './scheduled-updates.component.html',
  styleUrls: ['./scheduled-updates.component.scss'],
})
export class ScheduledUpdatesComponent implements OnInit, OnDestroy {
  private readonly svc = inject(ScheduledUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly snack = inject(MatSnackBar);

  jobs: ScheduledJob[] = [];
  alerts: JobAlert[] = [];
  window: WindowStatus | null = null;
  loading = true;

  ngOnInit(): void {
    // Hot streams — component re-renders on every update.
    this.svc.jobs$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((jobs) => {
      this.jobs = jobs;
    });
    this.svc.alerts$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((alerts) => {
      this.alerts = alerts;
    });
    this.svc.windowStatus$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((window) => {
        this.window = window;
      });

    // Initial snapshots + live WS stream.
    // Reset `loading` on BOTH `complete` AND `error` so a failed initial
    // fetch (auth, 5xx, network blip) doesn't leave the spinner stuck
    // forever. The hot streams above will keep re-rendering once data
    // arrives via the realtime WS.
    this.svc.refreshJobs().subscribe({
      complete: () => (this.loading = false),
      error: (err) => {
        this.loading = false;
        console.warn('scheduled-updates refreshJobs failed', err);
      },
    });
    this.svc.refreshAlerts().subscribe({
      error: (err) => console.warn('scheduled-updates refreshAlerts failed', err),
    });
    this.svc.refreshWindowStatus().subscribe({
      error: (err) => console.warn('scheduled-updates refreshWindowStatus failed', err),
    });
    this.svc.startRealtimeStream();
  }

  ngOnDestroy(): void {
    this.svc.stopRealtimeStream();
  }

  // ── Section-derived views ──────────────────────────────────────────

  get activeAlerts(): JobAlert[] {
    return this.alerts.filter((a) => a.is_active);
  }

  get activeAlertCount(): number {
    return this.activeAlerts.length;
  }

  get runningJob(): ScheduledJob | null {
    return this.jobs.find((j) => j.state === 'running') ?? null;
  }

  get pausedJob(): ScheduledJob | null {
    return this.jobs.find((j) => j.state === 'paused') ?? null;
  }

  get missedJobs(): ScheduledJob[] {
    return this.jobs.filter((j) => j.state === 'missed');
  }

  get pendingJobs(): ScheduledJob[] {
    return this.jobs.filter((j) => j.state === 'pending');
  }

  // ── Operator actions ───────────────────────────────────────────────

  pause(job: ScheduledJob): void {
    this.svc.pauseJob(job.id).subscribe();
  }

  resume(job: ScheduledJob): void {
    this.svc.resumeJob(job.id).subscribe();
  }

  cancel(job: ScheduledJob): void {
    this.svc.cancelJob(job.id).subscribe();
  }

  runNow(job: ScheduledJob): void {
    this.svc.runNow(job.id).subscribe({
      next: () => {
        this.snack.open(
          `${job.display_name}: queued for the next runner tick.`,
          'OK',
          { duration: 4000 },
        );
      },
      error: (err: HttpErrorResponse) => {
        // 409 CONFLICT is the window-guard / overflow refusal from the
        // backend. Surface the detail string so the operator knows why.
        const msg =
          err?.status === 409 && err.error?.detail
            ? err.error.detail
            : `Could not queue ${job.display_name} — ${err?.statusText || 'unknown error'}.`;
        this.snack.open(msg, 'Dismiss', { duration: 6000 });
      },
    });
  }

  ackAlert(alert: JobAlert): void {
    this.svc.acknowledgeAlert(alert.id).subscribe();
  }

  trackByJobId = (_idx: number, job: ScheduledJob) => job.id;
  trackByAlertId = (_idx: number, alert: JobAlert) => alert.id;
}
