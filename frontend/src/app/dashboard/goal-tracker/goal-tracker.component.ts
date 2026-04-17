import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnChanges,
  OnInit,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { DashboardData } from '../dashboard.service';

/**
 * Phase D3 — combined Daily Goal widget covering:
 *   - Gap 174 Daily Goal Tracker (user sets target, sees progress)
 *   - Gap 175 Milestone micro-animation (celebratory pulse on hit)
 *   - Gap 180 "Done for today?" checklist summary (green-tick when goal met)
 *
 * The user picks a daily goal for "approved suggestions today" — the
 * single most actionable noob KPI. The component reads progress from
 * DashboardData (today's `approved` count vs the start-of-day count
 * captured locally), shows a progress bar, and pulses a celebration
 * banner the first time the goal is hit on a given day.
 */

const GOAL_KEY = 'xfil_daily_goal_value';
const BASELINE_KEY = 'xfil_daily_goal_baseline';
const HIT_KEY = 'xfil_daily_goal_hit';

@Component({
  selector: 'app-goal-tracker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatProgressBarModule,
  ],
  template: `
    <mat-card class="gt-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="gt-avatar">flag</mat-icon>
        <mat-card-title>Today's goal</mat-card-title>
        <mat-card-subtitle>Approved suggestions target</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (editingGoal()) {
          <form (submit)="saveGoal($event)" class="gt-form">
            <mat-form-field appearance="outline" class="gt-field">
              <mat-label>Daily target (approvals)</mat-label>
              <input
                matInput
                autocomplete="off"
                type="number"
                min="1"
                [(ngModel)]="goalDraft"
                name="gt-goal"
              />
            </mat-form-field>
            <button
              mat-flat-button
              color="primary"
              type="submit"
              [disabled]="goalDraft < 1"
            >
              Save
            </button>
          </form>
        } @else {
          <div class="gt-progress-row">
            <span class="gt-progress-num">
              {{ progressToday() }} / {{ goal() }}
            </span>
            <button
              mat-icon-button
              type="button"
              matTooltip="Edit daily goal"
              (click)="startEdit()"
            >
              <mat-icon>edit</mat-icon>
            </button>
          </div>
          <mat-progress-bar
            mode="determinate"
            [value]="percent()"
            [class.gt-bar-done]="achieved()"
          />
          @if (achieved()) {
            <p class="gt-celebrate" [class.gt-pulse]="celebrating()">
              <mat-icon class="gt-celebrate-icon">check_circle</mat-icon>
              Done for today — goal hit. 🎉
            </p>
          } @else {
            <p class="gt-hint">
              {{ remaining() }} more to hit your goal.
            </p>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .gt-card { height: 100%; }
    .gt-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .gt-progress-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }
    .gt-progress-num {
      font-size: 22px;
      font-weight: 500;
      color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
    }
    .gt-form {
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }
    .gt-field { flex: 1; }
    mat-progress-bar {
      height: 8px;
      border-radius: 4px;
      overflow: hidden;
    }
    .gt-bar-done ::ng-deep .mdc-linear-progress__bar-inner {
      border-color: var(--color-success, #1e8e3e) !important;
    }
    .gt-celebrate {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 12px 0 0;
      padding: 8px 12px;
      background: var(--color-success-light, rgba(30, 142, 62, 0.10));
      color: var(--color-success-dark, #137333);
      border-radius: var(--card-border-radius, 8px);
      font-weight: 500;
      font-size: 13px;
    }
    .gt-celebrate-icon { color: var(--color-success, #1e8e3e); }
    .gt-pulse {
      animation: gt-pulse 1.2s ease 0s 2;
    }
    .gt-hint {
      margin: 12px 0 0;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    @keyframes gt-pulse {
      0%   { transform: scale(1); }
      50%  { transform: scale(1.05); }
      100% { transform: scale(1); }
    }
    @media (prefers-reduced-motion: reduce) {
      .gt-pulse { animation: none; }
    }
  `],
})
export class GoalTrackerComponent implements OnInit, OnChanges {
  @Input() set data(next: DashboardData | null | undefined) {
    this._data.set(next ?? null);
  }
  private readonly _data = signal<DashboardData | null>(null);

  readonly goal = signal<number>(10);
  readonly editingGoal = signal<boolean>(false);
  goalDraft = 10;
  readonly celebrating = signal<boolean>(false);

  /** Approved-today count: today's total approved minus the snapshot
   *  we took at start-of-day (so we don't credit yesterday's wins). */
  readonly progressToday = computed(() => {
    const data = this._data();
    if (!data) return 0;
    const total = data.suggestion_counts?.approved ?? 0;
    const baseline = this.readBaseline();
    return Math.max(0, total - baseline);
  });

  readonly percent = computed(() => {
    const g = this.goal();
    if (g <= 0) return 0;
    return Math.min(100, Math.round((this.progressToday() / g) * 100));
  });

  readonly achieved = computed(() => this.progressToday() >= this.goal());
  readonly remaining = computed(() =>
    Math.max(0, this.goal() - this.progressToday()),
  );

  ngOnInit(): void {
    this.goal.set(this.readGoal());
    this.goalDraft = this.goal();
  }

  ngOnChanges(): void {
    const data = this._data();
    if (!data) return;
    // First time we see data on a new local day, snapshot the
    // approved-total so today's progress is computed against it.
    this.ensureBaseline(data.suggestion_counts?.approved ?? 0);
    // Celebration: trigger once per day when goal is first hit.
    this.maybeCelebrate();
  }

  startEdit(): void {
    this.goalDraft = this.goal();
    this.editingGoal.set(true);
  }

  saveGoal(event: Event): void {
    event.preventDefault();
    const v = Math.max(1, Math.floor(this.goalDraft || 1));
    this.goal.set(v);
    try { localStorage.setItem(GOAL_KEY, String(v)); } catch { /* no-op */ }
    this.editingGoal.set(false);
  }

  // ── persistence helpers ────────────────────────────────────────────

  private readGoal(): number {
    try {
      const raw = localStorage.getItem(GOAL_KEY);
      const n = raw ? Number.parseInt(raw, 10) : NaN;
      return Number.isFinite(n) && n >= 1 ? n : 10;
    } catch {
      return 10;
    }
  }

  private readBaseline(): number {
    try {
      const raw = localStorage.getItem(BASELINE_KEY);
      if (!raw) return 0;
      const obj = JSON.parse(raw) as { date: string; value: number };
      if (obj?.date !== this.todayKey()) return 0;
      return typeof obj.value === 'number' ? obj.value : 0;
    } catch {
      return 0;
    }
  }

  private ensureBaseline(currentTotal: number): void {
    try {
      const raw = localStorage.getItem(BASELINE_KEY);
      const obj = raw ? (JSON.parse(raw) as { date: string; value: number }) : null;
      if (!obj || obj.date !== this.todayKey()) {
        localStorage.setItem(
          BASELINE_KEY,
          JSON.stringify({ date: this.todayKey(), value: currentTotal }),
        );
      }
    } catch {
      // No-op.
    }
  }

  private maybeCelebrate(): void {
    if (!this.achieved()) return;
    try {
      const today = this.todayKey();
      const last = localStorage.getItem(HIT_KEY);
      if (last === today) return; // already celebrated today
      localStorage.setItem(HIT_KEY, today);
    } catch {
      // No-op.
    }
    this.celebrating.set(true);
    setTimeout(() => this.celebrating.set(false), 3000);
  }

  private todayKey(): string {
    const d = new Date();
    return `${d.getFullYear()}-${(d.getMonth() + 1)
      .toString()
      .padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`;
  }
}
