import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DashboardData } from '../dashboard.service';
import { ExplainBadgeComponent } from '../../shared/ui/explain-badge/explain-badge.component';
import { ExplainNumberComponent } from '../../shared/ui/explain-number/explain-number.component';
import { ExplainNumberInput } from '../../shared/ui/explain-number/explain-number.types';
import { WhyFooterComponent } from '../../shared/ui/why-footer/why-footer.component';

/**
 * Phase D1 / Gap 63 — Single 0-100 Health Score Dial.
 *
 * Distills system health into one number that anyone can read in two
 * seconds. Color-coded (green/amber/red) and clickable to drill in to
 * the full Health page.
 *
 * Score formula (deliberately simple — composability beats accuracy):
 *
 *   score = 100
 *         - 30 if any service is "down"
 *         - 15 per "warning" or "stale" service (capped at 30)
 *         - 10 if there are unacknowledged urgent alerts
 *         - 5 per 50 open broken links (capped at 20)
 *
 * Result is clamped to [0, 100]. The exact weights are arbitrary but
 * stable across sessions so trends mean something. The threshold
 * boundaries match the GA4 color tokens (green ≥ 80, amber 50-79,
 * red < 50).
 *
 * Future: a follow-up gap can promote the formula to a backend-derived
 * `health_score` field on /api/dashboard/. For now, computing
 * client-side avoids a new endpoint.
 */
@Component({
  selector: 'app-health-score-dial',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    ExplainBadgeComponent,
    ExplainNumberComponent,
    WhyFooterComponent,
  ],
  template: `
    <mat-card class="hsd-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="hsd-avatar">monitor_heart</mat-icon>
        <mat-card-title>
          Health Score
          <app-explain-badge
            explanation="One number from 0 to 100 summarising overall system health. Subtracts points for: any service down (-30), each warning (-15 up to -30), urgent alerts active (-10), and accumulated broken links (up to -20)."
          />
          <app-explain-number [data]="explainInput()" />
        </mat-card-title>
        <mat-card-subtitle>{{ verdict() }}</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <div class="hsd-dial-wrap" [matTooltip]="breakdown()">
          <svg
            class="hsd-dial"
            viewBox="0 0 120 120"
            role="img"
            [attr.aria-label]="'Health score ' + score() + ' out of 100, ' + verdict()"
          >
            <!-- Background ring -->
            <circle cx="60" cy="60" r="50" class="hsd-track" />
            <!-- Foreground arc — stroke-dasharray drives the fill -->
            <circle
              cx="60"
              cy="60"
              r="50"
              class="hsd-progress"
              [class.hsd-good]="grade() === 'good'"
              [class.hsd-warn]="grade() === 'warn'"
              [class.hsd-bad]="grade() === 'bad'"
              [attr.stroke-dasharray]="dashArray()"
            />
            <text x="60" y="62" class="hsd-number" text-anchor="middle">
              {{ score() }}
            </text>
            <text x="60" y="82" class="hsd-suffix" text-anchor="middle">/ 100</text>
          </svg>
        </div>
      </mat-card-content>
      <mat-card-actions align="end">
        <a mat-button color="primary" routerLink="/health">
          Drill into Health
          <mat-icon iconPositionEnd>arrow_forward</mat-icon>
        </a>
      </mat-card-actions>
      <app-why-footer
        text="One number that summarises whether the system is OK at a glance. Refreshes whenever the dashboard re-fetches data." />
    </mat-card>
  `,
  styles: [`
    .hsd-card { height: 100%; }
    .hsd-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .hsd-dial-wrap {
      display: flex;
      justify-content: center;
      padding: 8px 0 16px;
    }
    .hsd-dial {
      width: 160px;
      height: 160px;
      transform: rotate(-90deg); /* start the arc at 12 o'clock */
    }
    .hsd-track {
      fill: none;
      stroke: var(--color-bg-faint);
      stroke-width: 12;
    }
    .hsd-progress {
      fill: none;
      stroke-width: 12;
      stroke-linecap: round;
      transition: stroke-dasharray 0.4s ease, stroke 0.2s ease;
    }
    .hsd-progress.hsd-good { stroke: var(--color-success, #1e8e3e); }
    .hsd-progress.hsd-warn { stroke: var(--color-warning, #f9ab00); }
    .hsd-progress.hsd-bad  { stroke: var(--color-error, #d93025); }
    .hsd-number {
      transform: rotate(90deg);
      transform-origin: 60px 60px;
      font-size: 28px;
      font-weight: 600;
      fill: var(--color-text-primary);
      font-family: var(--font-family);
    }
    .hsd-suffix {
      transform: rotate(90deg);
      transform-origin: 60px 60px;
      font-size: 11px;
      fill: var(--color-text-secondary);
      font-family: var(--font-family);
    }
    @media (prefers-reduced-motion: reduce) {
      .hsd-progress { transition: none; }
    }
  `],
})
export class HealthScoreDialComponent {
  /** Set by the dashboard parent on every refresh. */
  @Input() set data(next: DashboardData | null | undefined) {
    this._data.set(next ?? null);
  }
  /** Total open broken links — passed in separately because the
   *  dashboard fetches it on its own cadence. */
  @Input() set openBrokenLinks(n: number | null | undefined) {
    this._brokenLinks.set(n ?? 0);
  }
  /** Number of unacknowledged urgent alerts. */
  @Input() set urgentAlertCount(n: number | null | undefined) {
    this._urgentAlerts.set(n ?? 0);
  }

  private readonly _data = signal<DashboardData | null>(null);
  private readonly _brokenLinks = signal<number>(0);
  private readonly _urgentAlerts = signal<number>(0);

  readonly score = computed<number>(() => {
    const data = this._data();
    if (!data) return 0;

    let s = 100;
    const summary = data.system_health?.summary ?? {};

    const down = summary['down'] ?? 0;
    if (down > 0) s -= 30;

    const warnings = (summary['warning'] ?? 0) + (summary['stale'] ?? 0);
    s -= Math.min(warnings * 15, 30);

    if (this._urgentAlerts() > 0) s -= 10;

    const broken = this._brokenLinks();
    if (broken > 0) {
      s -= Math.min(Math.floor(broken / 50) * 5, 20);
    }

    return Math.max(0, Math.min(100, s));
  });

  readonly grade = computed<'good' | 'warn' | 'bad'>(() => {
    const s = this.score();
    if (s >= 80) return 'good';
    if (s >= 50) return 'warn';
    return 'bad';
  });

  readonly verdict = computed<string>(() => {
    switch (this.grade()) {
      case 'good': return 'Healthy — keep going';
      case 'warn': return 'Needs attention';
      case 'bad':  return 'Critical issues active';
    }
  });

  /** Stroke dasharray driving the SVG arc.
   *  Circumference = 2π·50 ≈ 314.159. */
  readonly dashArray = computed<string>(() => {
    const C = 2 * Math.PI * 50;
    const filled = (this.score() / 100) * C;
    return `${filled.toFixed(2)} ${(C - filled).toFixed(2)}`;
  });

  /** Tooltip showing why the score is what it is — for transparency. */
  readonly breakdown = computed<string>(() => {
    const data = this._data();
    if (!data) return 'No data yet.';
    const summary = data.system_health?.summary ?? {};
    const parts: string[] = [];
    parts.push(`${summary['healthy'] ?? 0} healthy`);
    parts.push(`${(summary['warning'] ?? 0) + (summary['stale'] ?? 0)} warning`);
    parts.push(`${summary['down'] ?? 0} down`);
    if (this._urgentAlerts() > 0) parts.push(`${this._urgentAlerts()} urgent alerts`);
    if (this._brokenLinks() > 0) parts.push(`${this._brokenLinks()} broken links`);
    return parts.join(' · ');
  });

  /** Phase D2 / Gap 77 — payload for the explain-number modal. */
  readonly explainInput = computed<ExplainNumberInput>(() => {
    const data = this._data();
    const summary = data?.system_health?.summary ?? {};
    const down = summary['down'] ?? 0;
    const warning = (summary['warning'] ?? 0) + (summary['stale'] ?? 0);
    const urgent = this._urgentAlerts();
    const broken = this._brokenLinks();
    const brokenPenalty = Math.min(Math.floor(broken / 50) * 5, 20);
    return {
      label: 'Health Score',
      value: this.score(),
      derivation:
        'Computed from system status, broken-link backlog, and unread urgent alerts. ' +
        'Starts at 100; loses points for each downstream issue.',
      formula:
        'score = 100\n' +
        '      - 30 if any service is down\n' +
        '      - 15 per warning (capped at -30)\n' +
        '      - 10 if there are unacknowledged urgent alerts\n' +
        '      -  5 per 50 open broken links (capped at -20)\n' +
        'final = clamp(score, 0, 100)',
      inputs: [
        { name: 'Services down', value: down },
        { name: 'Services warning / stale', value: warning },
        { name: 'Unacked urgent alerts', value: urgent },
        { name: 'Open broken links', value: broken },
        { name: 'Down penalty', value: down > 0 ? -30 : 0 },
        { name: 'Warning penalty', value: -Math.min(warning * 15, 30) },
        { name: 'Urgent alert penalty', value: urgent > 0 ? -10 : 0 },
        { name: 'Broken-link penalty', value: -brokenPenalty },
      ],
      drillRoute: '/health',
      drillLabel: 'Open System Health',
    };
  });
}
