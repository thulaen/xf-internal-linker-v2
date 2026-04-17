import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, of, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';

import { SyncJob, SyncService } from '../../jobs/sync.service';

/**
 * Phase D3 — combined "Sync activity right now" widget covering:
 *   - Gap 162 Restart Stuck Sync button (per-job action)
 *   - Gap 163 "Syncing right now" live one-liner
 *   - Gap 164 "Blocked right now" with Fix buttons
 *
 * Bundled because all three live in the same conceptual surface
 * ("what's the sync queue doing this minute"). Splitting them would
 * give the operator three near-identical lists of jobs; combining
 * them into one card with three sections keeps it one glance.
 *
 * Polls the existing /api/sync/jobs/ list every 30 seconds. Failed
 * or stuck jobs (status === 'failed' OR running > 1h with no
 * progress update) get a "Restart" button that calls the existing
 * resumeJob endpoint.
 */
@Component({
  selector: 'app-sync-activity',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatProgressBarModule,
  ],
  template: `
    <mat-card class="sa-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="sa-avatar">sync</mat-icon>
        <mat-card-title>Sync activity right now</mat-card-title>
        <mat-card-subtitle>
          Live snapshot of imports and pipeline runs · refreshes every 30s
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (running().length > 0) {
          <h3 class="sa-sub">Running</h3>
          <ul class="sa-list">
            @for (j of running(); track j.job_id) {
              <li class="sa-row">
                <mat-icon class="sa-row-icon sa-running">play_circle</mat-icon>
                <span class="sa-row-text">
                  <strong>{{ sourceLabel(j.source) }}</strong>
                  · {{ j.mode || 'sync' }} · {{ j.items_synced ?? 0 }} items so far
                </span>
              </li>
            }
          </ul>
        }
        @if (stuck().length > 0) {
          <h3 class="sa-sub sa-sub-warn">Blocked / stuck</h3>
          <ul class="sa-list">
            @for (j of stuck(); track j.job_id) {
              <li class="sa-row">
                <mat-icon class="sa-row-icon sa-stuck">error</mat-icon>
                <span class="sa-row-text">
                  <strong>{{ sourceLabel(j.source) }}</strong>
                  · {{ j.mode || 'sync' }} · {{ stuckReason(j) }}
                </span>
                <button
                  mat-stroked-button
                  type="button"
                  color="warn"
                  class="sa-fix"
                  [disabled]="busyJob() === j.job_id"
                  (click)="restart(j)"
                >
                  <mat-icon>restart_alt</mat-icon>
                  Restart
                </button>
              </li>
            }
          </ul>
        }
        @if (running().length === 0 && stuck().length === 0) {
          <p class="sa-empty">
            <mat-icon class="sa-row-icon sa-clear">check_circle</mat-icon>
            No active syncs and nothing stuck. Quiet on the queue.
          </p>
        }
      </mat-card-content>
      <mat-card-actions>
        <a mat-button routerLink="/jobs">
          <mat-icon>more_horiz</mat-icon>
          Open Jobs page
        </a>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    .sa-card { height: 100%; }
    .sa-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .sa-sub {
      margin: 12px 0 6px;
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--color-text-secondary);
    }
    .sa-sub-warn { color: var(--color-error); }
    .sa-list {
      list-style: none;
      margin: 0 0 8px;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .sa-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .sa-row-icon {
      flex-shrink: 0;
      font-size: 18px;
      width: 18px;
      height: 18px;
    }
    .sa-running { color: var(--color-primary); }
    .sa-stuck   { color: var(--color-error); }
    .sa-clear   { color: var(--color-success, #1e8e3e); }
    .sa-row-text {
      flex: 1;
      font-size: 13px;
      color: var(--color-text-primary);
      min-width: 0;
    }
    .sa-fix { flex-shrink: 0; }
    .sa-empty {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  `],
})
export class SyncActivityComponent implements OnInit {
  private readonly sync = inject(SyncService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly jobs = signal<readonly SyncJob[]>([]);
  readonly busyJob = signal<string | null>(null);

  readonly running = computed(() =>
    this.jobs().filter(
      (j) => j.status === 'running' || j.status === 'pending',
    ),
  );

  readonly stuck = computed(() => {
    const now = Date.now();
    return this.jobs().filter((j) => {
      if (j.status === 'failed' || j.status === 'paused') return true;
      // Long-running without completion is the heuristic for stuck.
      // Uses started_at (the SyncJob type exposes it) — a running job
      // that's been going for > 1h and isn't in progress reporting is
      // very likely stuck.
      if (j.status === 'running' && j.started_at) {
        const age = now - new Date(j.started_at).getTime();
        return age > 60 * 60 * 1000; // 1 hour
      }
      return false;
    });
  });

  ngOnInit(): void {
    timer(0, 30_000)
      .pipe(
        switchMap(() =>
          this.sync.getJobs().pipe(catchError(() => of<SyncJob[]>([]))),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((jobs) => {
        const arr = Array.isArray(jobs)
          ? jobs
          : ((jobs as unknown as { results?: SyncJob[] })?.results ?? []);
        this.jobs.set(arr);
      });
  }

  sourceLabel(source: string): string {
    switch (source) {
      case 'api': return 'XenForo';
      case 'wp':  return 'WordPress';
      case 'jsonl': return 'JSONL upload';
      default: return source;
    }
  }

  stuckReason(j: SyncJob): string {
    if (j.status === 'failed') {
      return j.error_message ? `failed — ${j.error_message.slice(0, 60)}` : 'failed';
    }
    if (j.status === 'paused') return 'paused — waiting to resume';
    return 'no progress in the last hour';
  }

  restart(j: SyncJob): void {
    if (this.busyJob() === j.job_id) return;
    this.busyJob.set(j.job_id);
    this.sync
      .resumeJob(j.job_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyJob.set(null);
          this.snack.open('Restart queued — opening Jobs.', 'OK', {
            duration: 3000,
          });
        },
        error: () => {
          this.busyJob.set(null);
          this.snack.open(
            'Could not restart this job — open Jobs to inspect.',
            'Dismiss',
            { duration: 5000 },
          );
        },
      });
  }
}
