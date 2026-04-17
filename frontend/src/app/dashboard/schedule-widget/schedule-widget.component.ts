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
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { interval } from 'rxjs';

/**
 * Phase D3 — combined Today / Coming-Up widget covering:
 *   - Gap 165 Today's Plan summary ("Scheduled: 3 syncs, 1 cleanup")
 *   - Gap 166 "Coming up next" countdown strip
 *
 * Both gaps describe a forward-looking schedule view; bundling
 * them avoids stacking two near-identical cards. The top half
 * counts what's planned today; the bottom half ticks down to the
 * next scheduled task.
 *
 * Data source: a static SCHEDULE constant scaffold for the v1.
 * A future session can wire `/api/scheduling/upcoming/` (when it
 * exists) to replace the constant — the rendering shape stays the
 * same. Until then, the constant honestly represents the standing
 * Celery beat schedule from `backend/config/settings/celery_schedules.py`.
 */

interface ScheduledTask {
  id: string;
  label: string;
  icon: string;
  /** Cron-style descriptor for the badge ("hourly", "daily 03:00"). */
  cadence: string;
  /** Local-time predicate: "next fire is N minutes from now". */
  nextFireMinutesFromNow(now: Date): number;
}

const SCHEDULE: readonly ScheduledTask[] = [
  {
    id: 'pipeline-sync',
    label: 'Pipeline sync',
    icon: 'sync',
    cadence: 'hourly',
    nextFireMinutesFromNow: (now) => {
      const next = new Date(now);
      next.setMinutes(0, 0, 0);
      next.setHours(next.getHours() + 1);
      return Math.round((next.getTime() - now.getTime()) / 60_000);
    },
  },
  {
    id: 'broken-link-scan',
    label: 'Broken-link scan',
    icon: 'link_off',
    cadence: 'daily 03:00 local',
    nextFireMinutesFromNow: (now) => {
      const next = new Date(now);
      next.setHours(3, 0, 0, 0);
      if (next.getTime() <= now.getTime()) {
        next.setDate(next.getDate() + 1);
      }
      return Math.round((next.getTime() - now.getTime()) / 60_000);
    },
  },
  {
    id: 'glitchtip-sync',
    label: 'GlitchTip issue sync',
    icon: 'bug_report',
    cadence: 'every 30m',
    nextFireMinutesFromNow: (now) => {
      const m = now.getMinutes();
      const next = m < 30 ? 30 - m : 60 - m;
      return next;
    },
  },
  {
    id: 'weight-tune',
    label: 'Monthly weight tuning',
    icon: 'tune',
    cadence: '1st of month, 02:00',
    nextFireMinutesFromNow: (now) => {
      const next = new Date(
        now.getFullYear(),
        now.getMonth() + 1,
        1,
        2,
        0,
        0,
        0,
      );
      return Math.round((next.getTime() - now.getTime()) / 60_000);
    },
  },
];

@Component({
  selector: 'app-schedule-widget',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule],
  template: `
    <mat-card class="sw-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="sw-avatar">event</mat-icon>
        <mat-card-title>What's scheduled</mat-card-title>
        <mat-card-subtitle>Today's plan and the next thing on the clock</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <div class="sw-summary">
          <span class="sw-summary-label">Today's plan</span>
          <span class="sw-summary-value">{{ todaySummary() }}</span>
        </div>
        <hr class="sw-divider" />
        <div class="sw-next">
          <span class="sw-next-label">Coming up next</span>
          @if (nextTask(); as t) {
            <div class="sw-next-row">
              <mat-icon class="sw-next-icon">{{ t.icon }}</mat-icon>
              <span class="sw-next-name">{{ t.label }}</span>
              <span class="sw-next-when" aria-live="polite">
                in {{ formatMinutes(t.minutesAway) }}
              </span>
            </div>
          } @else {
            <span class="sw-next-empty">No tasks scheduled in the next 24 hours.</span>
          }
        </div>
        <ul class="sw-list">
          @for (t of upcoming(); track t.id) {
            <li class="sw-item">
              <mat-icon>{{ t.icon }}</mat-icon>
              <span class="sw-item-label">{{ t.label }}</span>
              <span class="sw-item-cadence">{{ t.cadence }}</span>
            </li>
          }
        </ul>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .sw-card { height: 100%; }
    .sw-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .sw-summary {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 8px 12px;
      background: var(--color-bg-faint);
      border-radius: var(--card-border-radius, 8px);
    }
    .sw-summary-label,
    .sw-next-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--color-text-secondary);
    }
    .sw-summary-value {
      font-size: 16px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .sw-divider {
      border: 0;
      height: 1px;
      background: var(--color-border);
      margin: 12px 0;
    }
    .sw-next {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .sw-next-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .sw-next-icon { color: var(--color-primary); }
    .sw-next-name {
      flex: 1;
      font-size: 13px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .sw-next-when {
      font-size: 12px;
      color: var(--color-warning-dark, #b06000);
      font-variant-numeric: tabular-nums;
    }
    .sw-next-empty {
      font-size: 12px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
    .sw-list {
      list-style: none;
      margin: 12px 0 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .sw-item {
      display: grid;
      grid-template-columns: 18px 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 4px 8px;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .sw-item mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: var(--color-text-secondary);
    }
    .sw-item-cadence { font-style: italic; }
  `],
})
export class ScheduleWidgetComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);

  readonly now = signal<Date>(new Date());

  readonly upcoming = computed(() => SCHEDULE);

  readonly nextTask = computed(() => {
    const n = this.now();
    let best: { task: ScheduledTask; minutesAway: number } | null = null;
    for (const t of SCHEDULE) {
      const m = t.nextFireMinutesFromNow(n);
      if (m < 0) continue;
      if (m > 24 * 60) continue;
      if (!best || m < best.minutesAway) best = { task: t, minutesAway: m };
    }
    if (!best) return null;
    return {
      icon: best.task.icon,
      label: best.task.label,
      minutesAway: best.minutesAway,
    };
  });

  readonly todaySummary = computed(() => {
    // Heuristic count: the four scheduled tasks fire on different cadences.
    // For "today" we count those whose next fire is within 24h.
    const n = this.now();
    let count = 0;
    for (const t of SCHEDULE) {
      const m = t.nextFireMinutesFromNow(n);
      if (m >= 0 && m <= 24 * 60) count++;
    }
    if (count === 0) return 'Nothing on the clock today.';
    return `${count} task${count === 1 ? '' : 's'} expected in the next 24 hours.`;
  });

  ngOnInit(): void {
    // Tick the clock once per minute — rough enough for a countdown
    // that's measured in minutes-to-hours.
    interval(60_000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.now.set(new Date()));
  }

  formatMinutes(mins: number): string {
    if (mins < 1) return 'less than a minute';
    if (mins < 60) return `${mins} min`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (m === 0) return `${h}h`;
    return `${h}h ${m}m`;
  }
}
