import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';

import { TodayAction } from '../today-focus/today-focus.component';

/**
 * Phase D1 / Gap 65 — Dashboard-only priority summary bell.
 *
 * Distinct from the global notification center in the toolbar:
 *   - Toolbar notification center = HISTORICAL alerts (read/unread).
 *   - Priority Summary Bell = LIVE counts of urgent vs informational
 *     items currently visible on the dashboard, presented as a single
 *     glanceable badge.
 *
 * The badge color escalates: green (no urgent), amber (warnings only),
 * red (≥1 urgent). Click to open a menu listing the top urgent items.
 *
 * Inputs are deliberately minimal — the parent dashboard already has
 * the action list, we just summarize it.
 */
@Component({
  selector: 'app-priority-summary-bell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatIconModule,
    MatBadgeModule,
    MatButtonModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  template: `
    <button
      mat-icon-button
      class="psb-button"
      [class.psb-urgent]="grade() === 'urgent'"
      [class.psb-warning]="grade() === 'warning'"
      [class.psb-clear]="grade() === 'clear'"
      [matMenuTriggerFor]="menu"
      [matTooltip]="tooltip()"
      [matBadge]="totalCount() || ''"
      [matBadgeHidden]="totalCount() === 0"
      [matBadgeColor]="grade() === 'urgent' ? 'warn' : 'accent'"
      matBadgeSize="small"
      aria-label="Dashboard priority summary"
      type="button"
    >
      <mat-icon>{{ icon() }}</mat-icon>
    </button>
    <mat-menu #menu="matMenu" xPosition="before">
      <div class="psb-menu" (click)="$event.stopPropagation()">
        <header class="psb-menu-header">
          <strong>{{ headline() }}</strong>
          <span class="psb-menu-sub">{{ subline() }}</span>
        </header>
        @if (urgent().length > 0) {
          <ul class="psb-list">
            @for (a of urgent(); track a.title) {
              <li class="psb-item psb-item-urgent">
                <mat-icon>error</mat-icon>
                <span>{{ a.title }}</span>
              </li>
            }
          </ul>
        }
        @if (info().length > 0) {
          <ul class="psb-list">
            @for (a of info(); track a.title) {
              <li class="psb-item psb-item-info">
                <mat-icon>info</mat-icon>
                <span>{{ a.title }}</span>
              </li>
            }
          </ul>
        }
        @if (urgent().length === 0 && info().length === 0) {
          <p class="psb-empty">No items requiring attention.</p>
        }
      </div>
    </mat-menu>
  `,
  styles: [`
    .psb-button {
      transition: color 0.2s ease;
    }
    .psb-button.psb-clear { color: var(--color-success, #1e8e3e); }
    .psb-button.psb-warning { color: var(--color-warning, #f9ab00); }
    .psb-button.psb-urgent { color: var(--color-error, #d93025); }

    .psb-menu {
      min-width: 280px;
      max-width: 360px;
      padding: 12px 16px;
    }
    .psb-menu-header {
      display: flex;
      flex-direction: column;
      gap: 2px;
      margin-bottom: 8px;
    }
    .psb-menu-sub {
      font-size: 11px;
      color: var(--color-text-secondary);
    }
    .psb-list {
      list-style: none;
      margin: 0 0 8px;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .psb-item {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      font-size: 12px;
      line-height: 1.4;
      color: var(--color-text-primary);
    }
    .psb-item mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      flex-shrink: 0;
      margin-top: 1px;
    }
    .psb-item-urgent mat-icon { color: var(--color-error); }
    .psb-item-info mat-icon { color: var(--color-primary); }
    .psb-empty {
      margin: 0;
      font-size: 12px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
    @media (prefers-reduced-motion: reduce) {
      .psb-button { transition: none; }
    }
  `],
})
export class PrioritySummaryBellComponent {
  /** All visible action items (the same list used by today-focus). */
  @Input() set actions(next: readonly TodayAction[] | null | undefined) {
    this._actions.set(next ?? []);
  }

  private readonly _actions = signal<readonly TodayAction[]>([]);

  readonly urgent = computed(() =>
    this._actions().filter((a) => a.severity === 'error' || a.isBlocking),
  );
  readonly info = computed(() =>
    this._actions().filter(
      (a) => a.severity !== 'error' && !a.isBlocking,
    ),
  );

  readonly totalCount = computed(() => this._actions().length);

  readonly grade = computed<'clear' | 'warning' | 'urgent'>(() => {
    if (this.urgent().length > 0) return 'urgent';
    if (this.info().length > 0) return 'warning';
    return 'clear';
  });

  readonly icon = computed<string>(() => {
    switch (this.grade()) {
      case 'urgent': return 'notifications_active';
      case 'warning': return 'notifications';
      case 'clear': return 'notifications_none';
    }
  });

  readonly headline = computed<string>(() => {
    const u = this.urgent().length;
    const i = this.info().length;
    if (u > 0) return `${u} urgent · ${i} informational`;
    if (i > 0) return `${i} informational item${i === 1 ? '' : 's'}`;
    return 'All clear';
  });

  readonly subline = computed<string>(() => {
    if (this.grade() === 'urgent') {
      return 'Click an urgent row to drill in.';
    }
    if (this.grade() === 'warning') {
      return 'Things to look at, none urgent.';
    }
    return 'Nothing requires your attention right now.';
  });

  readonly tooltip = computed<string>(() => {
    const u = this.urgent().length;
    if (u > 0) return `${u} urgent dashboard items — click for details`;
    return 'Dashboard priority summary';
  });
}
