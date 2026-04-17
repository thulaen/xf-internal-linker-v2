import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DashboardData } from '../dashboard.service';

/**
 * Phase D3 / Gap 156 — Pinned single-metric ticker.
 *
 * A sticky one-line strip showing ONE always-visible number (active
 * issues count). Sticks to the viewport top so the operator sees it
 * even when scrolled past the dashboard hero.
 *
 * "Active issues" = down services + warning services + unacked urgent
 * alerts + open broken links. We avoid the dial's score formula here
 * — the ticker is binary: there are issues, or there aren't.
 *
 * The chip background goes red when issues > 0 so the user can spot
 * the change without looking away from the chart they're scrolling.
 */
@Component({
  selector: 'app-metric-ticker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, RouterLink, MatIconModule, MatTooltipModule],
  template: `
    <a
      class="mt"
      [class.mt-clear]="issues() === 0"
      [class.mt-active]="issues() > 0"
      routerLink="/health"
      [matTooltip]="tooltip()"
      role="status"
      aria-live="polite"
    >
      <mat-icon class="mt-icon" aria-hidden="true">
        {{ issues() === 0 ? 'check_circle' : 'error' }}
      </mat-icon>
      <span class="mt-text">
        Active issues: <strong>{{ issues() }}</strong>
      </span>
    </a>
  `,
  styles: [`
    .mt {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      text-decoration: none;
      transition: background-color 0.2s ease, color 0.2s ease;
      border: var(--card-border);
      width: fit-content;
    }
    .mt-clear {
      background: var(--color-success-light, rgba(30, 142, 62, 0.08));
      color: var(--color-success-dark, #137333);
      border-color: var(--color-success, #1e8e3e);
    }
    .mt-active {
      background: var(--color-error-50, rgba(217, 48, 37, 0.08));
      color: var(--color-error-dark, #b3261e);
      border-color: var(--color-error, #d93025);
    }
    .mt-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .mt-text strong {
      font-variant-numeric: tabular-nums;
    }
    @media (prefers-reduced-motion: reduce) {
      .mt { transition: none; }
    }
  `],
})
export class MetricTickerComponent {
  @Input() set data(next: DashboardData | null | undefined) {
    this._data.set(next ?? null);
  }
  @Input() set openBrokenLinks(n: number | null | undefined) {
    this._broken.set(n ?? 0);
  }
  @Input() set urgentAlertCount(n: number | null | undefined) {
    this._urgent.set(n ?? 0);
  }

  private readonly _data = signal<DashboardData | null>(null);
  private readonly _broken = signal<number>(0);
  private readonly _urgent = signal<number>(0);

  readonly issues = computed<number>(() => {
    const data = this._data();
    const summary = data?.system_health?.summary ?? {};
    const down = summary['down'] ?? 0;
    const warning = (summary['warning'] ?? 0) + (summary['stale'] ?? 0);
    return down + warning + this._urgent() + this._broken();
  });

  readonly tooltip = computed<string>(() => {
    const data = this._data();
    if (!data) return 'No data yet — click to open System Health.';
    const summary = data.system_health?.summary ?? {};
    const parts = [
      `${summary['down'] ?? 0} down`,
      `${(summary['warning'] ?? 0) + (summary['stale'] ?? 0)} warning`,
      `${this._urgent()} urgent alerts`,
      `${this._broken()} broken links`,
    ];
    return `${parts.join(' · ')} — click to open System Health.`;
  });
}
