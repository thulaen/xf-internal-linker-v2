import {
  Component,
  ChangeDetectionStrategy,
  DestroyRef,
  effect,
  inject,
  input,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { catchError, of } from 'rxjs';
import {
  AnalyticsEngagementMixResponse,
  AnalyticsService,
} from '../analytics.service';

/**
 * Phase 2b — engagement mix card.
 *
 * Shows the Phase 2 engagement telemetry (quick_exit, dwell_30s, dwell_60s)
 * alongside the pre-existing engaged_sessions (10s threshold). Four KPI tiles
 * summarise tier-reach rates; a "tier reach" strip visualises each tier as
 * an independent horizontal bar (cumulative events — bars are not stacked).
 *
 * Re-fetches whenever the parent `source` or `windowDays` input signals
 * change, so it tracks the analytics page's filter toggles.
 */
interface Tier {
  label: string;
  rate: number;
  count: number;
  cssClass: string;
  tooltip: string;
}

@Component({
  selector: 'app-engagement-mix',
  standalone: true,
  imports: [
    MatCardModule,
    MatIconModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card class="engagement-mix-card" appearance="outlined">
      <mat-card-header>
        <mat-card-title class="card-title">
          <mat-icon class="title-icon">insights</mat-icon>
          <span>Engagement mix</span>
        </mat-card-title>
        <mat-card-subtitle>
          How many readers stick around vs bounce back.
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content class="card-body">
        @if (loading) {
          <div class="loading-wrap">
            <mat-spinner diameter="36"></mat-spinner>
          </div>
        } @else if (!data || data.totals.destination_views === 0) {
          <p class="empty-hint">
            No destination views yet in this window. Engagement signals start
            appearing once the browser bridge is installed and readers land
            on an instrumented page.
          </p>
        } @else {
          <div class="kpi-grid">
            @for (tier of tiers; track tier.label) {
              <div class="kpi-tile" [matTooltip]="tier.tooltip">
                <div class="kpi-value" [class]="tier.cssClass">
                  {{ formatPercent(tier.rate) }}
                </div>
                <div class="kpi-label">{{ tier.label }}</div>
                <div class="kpi-count">{{ tier.count }} of {{ totalViews }}</div>
              </div>
            }
          </div>
          <div class="tier-reach-strip">
            <p class="strip-caption">Tier reach (share of destination views)</p>
            @for (tier of tiers; track tier.label) {
              <div class="tier-row">
                <span class="tier-row-label">{{ tier.label }}</span>
                <div class="tier-row-track">
                  <div
                    class="tier-row-fill"
                    [class]="tier.cssClass"
                    [style.width.%]="tier.rate * 100"
                  ></div>
                </div>
                <span class="tier-row-pct">{{ formatPercent(tier.rate) }}</span>
              </div>
            }
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    :host { display: block; }
    .engagement-mix-card {
      border: var(--card-border);
      box-shadow: none;
    }
    .card-title {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .title-icon {
      color: var(--color-primary);
    }
    .card-body {
      padding: var(--space-md) var(--space-lg) var(--space-lg);
    }
    .loading-wrap {
      display: flex;
      justify-content: center;
      padding: var(--space-xl);
    }
    .empty-hint {
      color: var(--color-text-muted);
      text-align: center;
      padding: var(--space-lg);
      margin: 0;
    }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: var(--space-md);
      margin-bottom: var(--space-lg);
    }
    .kpi-tile {
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      padding: var(--space-md);
      background: var(--color-bg-white);
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
      cursor: default;
    }
    .kpi-value {
      font-size: 24px;
      font-weight: 500;
      color: var(--color-text-primary);
      line-height: 1.1;
    }
    .kpi-label {
      font-size: 12px;
      color: var(--color-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .kpi-count {
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .tier-reach-strip {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }
    .strip-caption {
      margin: 0 0 var(--space-xs) 0;
      color: var(--color-text-secondary);
      font-size: 12px;
    }
    .tier-row {
      display: grid;
      grid-template-columns: 120px 1fr 48px;
      align-items: center;
      gap: var(--space-sm);
    }
    .tier-row-label {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .tier-row-track {
      height: 12px;
      background: var(--color-bg-faint);
      border-radius: 4px;
      overflow: hidden;
    }
    .tier-row-fill {
      height: 100%;
      transition: width 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .tier-row-pct {
      font-size: 12px;
      color: var(--color-text-secondary);
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    /* Tier colours — quick-exit red, engagement ramp blue -> darker blue. */
    .tier-quick-exit { background: var(--color-error); color: var(--color-error); }
    .tier-engaged { background: var(--color-blue-50, #e8f0fe); color: var(--color-primary); }
    .tier-dwell-30 { background: var(--color-primary); color: var(--color-primary); }
    .tier-dwell-60 { background: #1967d2; color: #1967d2; }
    .kpi-value.tier-quick-exit { color: var(--color-error); }
    .kpi-value.tier-engaged { color: var(--color-primary); }
    .kpi-value.tier-dwell-30 { color: var(--color-primary); }
    .kpi-value.tier-dwell-60 { color: #1967d2; }
    @media (max-width: 960px) {
      .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  `],
})
export class EngagementMixComponent {
  private analytics = inject(AnalyticsService);
  private destroyRef = inject(DestroyRef);

  readonly source = input<'all' | 'ga4' | 'matomo'>('all');
  readonly windowDays = input<number>(30);

  data: AnalyticsEngagementMixResponse | null = null;
  loading = true;
  tiers: Tier[] = [];
  totalViews = 0;

  constructor() {
    effect(() => {
      // Read both signals so Angular retriggers on either change.
      const source = this.source();
      const days = this.windowDays();
      this.load(source, days);
    });
  }

  private load(
    source: 'all' | 'ga4' | 'matomo',
    days: number,
  ): void {
    this.loading = true;
    this.analytics
      .getEngagementMix(source, days)
      .pipe(
        catchError(() => of(null)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((payload) => {
        this.data = payload;
        this.tiers = this.buildTiers(payload);
        this.totalViews = payload?.totals.destination_views ?? 0;
        this.loading = false;
      });
  }

  private buildTiers(payload: AnalyticsEngagementMixResponse | null): Tier[] {
    if (!payload) {
      return [];
    }
    const { totals, rates } = payload;
    return [
      {
        label: 'Quick exit',
        rate: rates.quick_exit_rate,
        count: totals.quick_exit_sessions,
        cssClass: 'tier-quick-exit',
        tooltip:
          'Readers who left within 5 seconds of landing on the destination. ' +
          'Strong negative signal — the link probably did not match intent.',
      },
      {
        label: 'Engaged 10s+',
        rate: rates.engaged_rate,
        count: totals.engaged_sessions,
        cssClass: 'tier-engaged',
        tooltip:
          'Readers who stayed engaged on the destination for at least 10 seconds.',
      },
      {
        label: 'Dwell 30s+',
        rate: rates.dwell_30s_rate,
        count: totals.dwell_30s_sessions,
        cssClass: 'tier-dwell-30',
        tooltip:
          'Readers who stayed on the destination for at least 30 seconds.',
      },
      {
        label: 'Dwell 60s+',
        rate: rates.dwell_60s_rate,
        count: totals.dwell_60s_sessions,
        cssClass: 'tier-dwell-60',
        tooltip:
          'Readers who stayed on the destination for at least 60 seconds. ' +
          'Strongest positive engagement signal.',
      },
    ];
  }

  formatPercent(rate: number): string {
    if (!rate || !Number.isFinite(rate)) {
      return '0.0%';
    }
    return `${(rate * 100).toFixed(1)}%`;
  }
}
