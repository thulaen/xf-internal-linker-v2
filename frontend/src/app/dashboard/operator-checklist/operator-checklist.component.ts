import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';

/**
 * Phase D2 / Gap 67 — Daily pre-flight Operator Checklist.
 *
 * A short list of things a noob operator should run through every
 * morning before they trust the dashboard:
 *   - Did you check alerts?
 *   - Did you preview the next pipeline run?
 *   - Did you approve pending suggestions?
 *
 * Check state persists in localStorage keyed by today's date, so
 * yesterday's ticks don't carry over. A new day shows a fresh blank
 * checklist and the previous day's check state is purged on view.
 *
 * The checklist is opinionated, not configurable — pre-flight items
 * are about discipline, and a noob who can't add their own items
 * shouldn't be able to remove them either.
 */

interface ChecklistItem {
  id: string;
  label: string;
  helper: string;
  route: string;
  fragment?: string;
  icon: string;
}

const CHECKLIST_ITEMS: readonly ChecklistItem[] = [
  {
    id: 'alerts',
    label: 'Check the Alerts page',
    helper: 'Read any unread urgent or error alerts; acknowledge or fix.',
    route: '/alerts',
    icon: 'notifications',
  },
  {
    id: 'health',
    label: 'Glance at System Health',
    helper: 'Confirm no service is down or in warning state.',
    route: '/health',
    icon: 'health_and_safety',
  },
  {
    id: 'preview',
    label: 'Preview the next pipeline run',
    helper: 'Open Jobs and review the Sync Preview before kicking off.',
    route: '/jobs',
    icon: 'preview',
  },
  {
    id: 'review',
    label: 'Approve pending link suggestions',
    helper: 'Drain the review queue so backlog stays under control.',
    route: '/review',
    icon: 'rate_review',
  },
  {
    id: 'broken',
    label: 'Scan for new broken links',
    helper: 'Run the broken-link scanner if it last ran more than 24h ago.',
    route: '/link-health',
    icon: 'link_off',
  },
];

const STORAGE_KEY = 'xfil_operator_checklist';

@Component({
  selector: 'app-operator-checklist',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatCheckboxModule,
    MatIconModule,
    MatButtonModule,
    MatProgressBarModule,
  ],
  template: `
    <mat-card class="oc-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="oc-avatar">checklist</mat-icon>
        <mat-card-title>Daily pre-flight</mat-card-title>
        <mat-card-subtitle>{{ checkedCount() }} of {{ items.length }} done today</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <mat-progress-bar
          mode="determinate"
          [value]="progressPercent()"
          class="oc-bar"
          [class.oc-bar-done]="checkedCount() === items.length"
        />
        <ul class="oc-list">
          @for (item of items; track item.id) {
            <li class="oc-item" [class.oc-checked]="checked()[item.id]">
              <mat-checkbox
                color="primary"
                [checked]="checked()[item.id]"
                (change)="toggle(item.id, $event.checked)"
              >
                <span class="oc-label">
                  <mat-icon class="oc-item-icon">{{ item.icon }}</mat-icon>
                  {{ item.label }}
                </span>
              </mat-checkbox>
              <p class="oc-helper">{{ item.helper }}</p>
              <a
                mat-button
                color="primary"
                [routerLink]="item.route"
                [fragment]="item.fragment ?? undefined"
                class="oc-go"
              >
                Go
                <mat-icon iconPositionEnd>arrow_forward</mat-icon>
              </a>
            </li>
          }
        </ul>
        @if (checkedCount() === items.length) {
          <p class="oc-done">
            <mat-icon class="oc-done-icon">celebration</mat-icon>
            Pre-flight complete. You're cleared for takeoff.
          </p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .oc-card { height: 100%; }
    .oc-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .oc-bar {
      margin-bottom: 12px;
      height: 6px;
      border-radius: 3px;
      overflow: hidden;
    }
    .oc-bar.oc-bar-done ::ng-deep .mdc-linear-progress__bar-inner {
      border-color: var(--color-success, #1e8e3e) !important;
    }
    .oc-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .oc-item {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 4px 12px;
      align-items: start;
      padding: 8px 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      transition: opacity 0.2s ease;
    }
    .oc-item.oc-checked {
      opacity: 0.65;
      background: var(--color-bg-faint);
    }
    .oc-label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .oc-checked .oc-label {
      text-decoration: line-through;
    }
    .oc-item-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: var(--color-primary);
    }
    .oc-helper {
      grid-column: 1 / 2;
      margin: 2px 0 0 32px;
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.4;
    }
    .oc-go {
      grid-column: 2;
      grid-row: 1 / span 2;
      align-self: center;
    }
    .oc-done {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 12px 0 0;
      padding: 8px 12px;
      background: var(--color-success-light, rgba(30, 142, 62, 0.08));
      color: var(--color-success-dark, #137333);
      border-radius: var(--card-border-radius, 8px);
      font-size: 13px;
      font-weight: 500;
    }
    .oc-done-icon {
      color: var(--color-success, #1e8e3e);
    }
    @media (prefers-reduced-motion: reduce) {
      .oc-item { transition: none; }
    }
  `],
})
export class OperatorChecklistComponent implements OnInit {
  readonly items = CHECKLIST_ITEMS;
  readonly checked = signal<Record<string, boolean>>({});

  readonly checkedCount = computed(
    () => Object.values(this.checked()).filter(Boolean).length,
  );
  readonly progressPercent = computed(() =>
    this.items.length === 0
      ? 0
      : Math.round((this.checkedCount() / this.items.length) * 100),
  );

  ngOnInit(): void {
    this.checked.set(this.readToday());
  }

  toggle(id: string, next: boolean): void {
    const updated = { ...this.checked(), [id]: next };
    this.checked.set(updated);
    this.persistToday(updated);
  }

  // ── persistence ────────────────────────────────────────────────────

  /** Read today's check state. Anything from older dates is purged so
   *  storage doesn't grow unbounded over months. */
  private readToday(): Record<string, boolean> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw) as { date?: string; checks?: Record<string, boolean> };
      if (parsed?.date !== this.todayKey()) {
        // Stale — purge and start fresh.
        localStorage.removeItem(STORAGE_KEY);
        return {};
      }
      return parsed.checks ?? {};
    } catch {
      return {};
    }
  }

  private persistToday(checks: Record<string, boolean>): void {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ date: this.todayKey(), checks }),
      );
    } catch {
      // Private mode — in-memory only is fine.
    }
  }

  private todayKey(): string {
    const d = new Date();
    const y = d.getFullYear();
    const m = (d.getMonth() + 1).toString().padStart(2, '0');
    const dd = d.getDate().toString().padStart(2, '0');
    return `${y}-${m}-${dd}`;
  }
}
