import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { DashboardData } from '../dashboard.service';

/**
 * Phase D3 — combined "instant health" card. Covers:
 *   - Gap 155: Weather-icon health glance (☀️/🌤️/⛈️ for sunny/mixed/storm)
 *   - Gap 173: YES / NO / ATTENTION giant status with huge text
 *
 * Both gaps want the same thing — a single oversized symbol that
 * answers "is the app okay?" from across the room. Splitting them
 * would put two redundant cards next to each other. Bundling gives the
 * user one giant verdict + an icon they can read at a glance.
 *
 * Inputs:
 *   - data: full DashboardData (for system_health.summary).
 *   - urgentAlertCount: number of unacked urgent alerts (parent fetches).
 *
 * Verdict logic mirrors HealthScoreDial's grade thresholds for
 * consistency: green = healthy, amber = warning, red = critical.
 */
@Component({
  selector: 'app-instant-health',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule],
  template: `
    <mat-card class="ih-card" [class]="'ih-' + verdict()">
      <mat-card-content>
        <div class="ih-icon-row">
          <mat-icon class="ih-weather" aria-hidden="true">{{ weatherIcon() }}</mat-icon>
        </div>
        <div class="ih-verdict">{{ verdictWord() }}</div>
        <div class="ih-sub">{{ verdictSubtitle() }}</div>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .ih-card {
      height: 100%;
      text-align: center;
      transition: background-color 0.2s ease;
    }
    .ih-good { background: var(--color-success-light, rgba(30, 142, 62, 0.06)); }
    .ih-warn { background: var(--color-warning-light, rgba(249, 171, 0, 0.10)); }
    .ih-bad  { background: var(--color-error-50, rgba(217, 48, 37, 0.08)); }

    .ih-icon-row {
      display: flex;
      justify-content: center;
      padding-top: 12px;
    }
    .ih-weather {
      font-size: 64px;
      width: 64px;
      height: 64px;
    }
    .ih-good .ih-weather { color: var(--color-success, #1e8e3e); }
    .ih-warn .ih-weather { color: var(--color-warning, #f9ab00); }
    .ih-bad  .ih-weather { color: var(--color-error, #d93025); }

    .ih-verdict {
      font-size: 40px;
      font-weight: 700;
      letter-spacing: 2px;
      margin: 8px 0 4px;
    }
    .ih-good .ih-verdict { color: var(--color-success-dark, #137333); }
    .ih-warn .ih-verdict { color: var(--color-warning-dark, #b06000); }
    .ih-bad  .ih-verdict { color: var(--color-error-dark, #b3261e); }

    .ih-sub {
      font-size: 12px;
      color: var(--color-text-secondary);
      padding: 0 12px 16px;
    }
    @media (prefers-reduced-motion: reduce) {
      .ih-card { transition: none; }
    }
  `],
})
export class InstantHealthComponent {
  @Input() set data(next: DashboardData | null | undefined) {
    this._data.set(next ?? null);
  }
  @Input() set urgentAlertCount(n: number | null | undefined) {
    this._urgent.set(n ?? 0);
  }

  private readonly _data = signal<DashboardData | null>(null);
  private readonly _urgent = signal<number>(0);

  readonly verdict = computed<'good' | 'warn' | 'bad'>(() => {
    const data = this._data();
    if (!data) return 'good';
    const summary = data.system_health?.summary ?? {};
    const down = summary['down'] ?? 0;
    const warning = (summary['warning'] ?? 0) + (summary['stale'] ?? 0);
    if (down > 0 || this._urgent() > 0) return 'bad';
    if (warning > 0) return 'warn';
    return 'good';
  });

  readonly verdictWord = computed<string>(() => {
    switch (this.verdict()) {
      case 'good': return 'YES';
      case 'warn': return 'ATTENTION';
      case 'bad':  return 'NO';
    }
  });

  readonly weatherIcon = computed<string>(() => {
    switch (this.verdict()) {
      case 'good': return 'wb_sunny';
      case 'warn': return 'cloud';
      case 'bad':  return 'thunderstorm';
    }
  });

  readonly verdictSubtitle = computed<string>(() => {
    switch (this.verdict()) {
      case 'good': return 'Everything is healthy right now.';
      case 'warn': return 'Some services degraded — worth a glance.';
      case 'bad':  return 'A critical issue is active. Open Health.';
    }
  });
}
