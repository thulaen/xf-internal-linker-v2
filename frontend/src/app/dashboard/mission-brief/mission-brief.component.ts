import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { catchError, of, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';

import { DashboardService, MissionBrief } from '../dashboard.service';

/**
 * Phase D1 / Gap 61 — Mission Brief card.
 *
 * Three sentences, generated server-side:
 *   1. Yesterday: counts of what the system did.
 *   2. Today: what's queued right now.
 *   3. Watch: the single most pressing thing, or "Nothing is on fire."
 *
 * Pinned at the top of the dashboard so it's the first thing a
 * returning operator reads. Refreshes every 15 minutes — this is a
 * briefing, not a live ticker, so a slower cadence is appropriate.
 *
 * Distinct from Status Story (Gap 53):
 *   - Mission Brief gives historical context (yesterday) + highest-
 *     priority fix.
 *   - Status Story is a rolling present-tense snapshot.
 */
@Component({
  selector: 'app-mission-brief',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <mat-card class="mb-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="mb-avatar">campaign</mat-icon>
        <mat-card-title>Mission Brief</mat-card-title>
        <mat-card-subtitle>Yesterday · Today · What to watch</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (loading() && !brief()) {
          <div class="mb-spinner">
            <mat-spinner diameter="24" />
          </div>
        } @else if (brief(); as b) {
          <ol class="mb-list">
            <li class="mb-sentence">
              <mat-icon class="mb-bullet">history</mat-icon>
              <span>{{ b.sentences[0] }}</span>
            </li>
            <li class="mb-sentence">
              <mat-icon class="mb-bullet">pending_actions</mat-icon>
              <span>{{ b.sentences[1] }}</span>
            </li>
            <li class="mb-sentence" [class.mb-watch]="!!b.top_alert">
              <mat-icon class="mb-bullet">{{ b.top_alert ? 'error' : 'check_circle' }}</mat-icon>
              <span>{{ b.sentences[2] }}</span>
              @if (b.top_alert; as alert) {
                <a
                  class="mb-alert-link"
                  [routerLink]="['/alerts', alert.alert_id]"
                >
                  Open alert
                  <mat-icon>arrow_forward</mat-icon>
                </a>
              }
            </li>
          </ol>
        } @else {
          <p class="mb-empty">Couldn't load the brief. We'll try again shortly.</p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .mb-card {
      border-left: 4px solid var(--color-primary);
    }
    .mb-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .mb-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .mb-sentence {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      font-size: 14px;
      line-height: 1.5;
      color: var(--color-text-primary);
    }
    .mb-sentence.mb-watch {
      background: var(--color-error-50, rgba(217, 48, 37, 0.05));
      padding: 8px 12px;
      border-radius: var(--card-border-radius, 8px);
    }
    .mb-watch .mb-bullet { color: var(--color-error); }
    .mb-bullet {
      flex-shrink: 0;
      color: var(--color-text-secondary);
      font-size: 18px;
      width: 18px;
      height: 18px;
      margin-top: 2px;
    }
    .mb-alert-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-left: auto;
      font-size: 12px;
      color: var(--color-error);
      text-decoration: none;
      white-space: nowrap;
    }
    .mb-alert-link:hover { text-decoration: underline; }
    .mb-alert-link mat-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    .mb-spinner {
      display: flex;
      justify-content: center;
      padding: 16px 0;
    }
    .mb-empty {
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
      margin: 0;
    }
  `],
})
export class MissionBriefComponent implements OnInit {
  private readonly dash = inject(DashboardService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly visibilityGate = inject(VisibilityGateService);

  readonly brief = signal<MissionBrief | null>(null);
  readonly loading = signal(false);

  ngOnInit(): void {
    // 15-minute refresh cadence — a brief, not a ticker. Gated by
    // `VisibilityGateService` so hidden tabs / signed-out sessions
    // skip the poll. See docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(0, 15 * 60 * 1000).pipe(
          switchMap(() => {
            this.loading.set(true);
            return this.dash
              .getMissionBrief()
              .pipe(catchError(() => of<MissionBrief | null>(null)));
          }),
        ),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((b) => {
        this.loading.set(false);
        if (b) this.brief.set(b);
      });
  }
}
