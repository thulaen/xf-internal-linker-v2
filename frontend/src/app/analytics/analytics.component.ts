import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnInit, inject, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatButtonToggleChange, MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration, ChartData } from 'chart.js';
import {
  AnalyticsBreakdownsResponse,
  AnalyticsFunnelResponse,
  AnalyticsGeoDetailResponse,
  AnalyticsHealthResponse,
  AnalyticsHealthSummary,
  AnalyticsIntegrationResponse,
  AnalyticsOverviewResponse,
  AnalyticsService,
  AnalyticsTopSuggestion,
  AnalyticsTopSuggestionsResponse,
  AnalyticsTrendPoint,
  AnalyticsTrendResponse,
  AnalyticsVersionComparisonResponse,
  AnalyticsVersionComparisonRow,
  GSCImpactSnapshot,
  SearchImpactDetailResponse,
} from './analytics.service';
import { FilterPersistenceService } from '../core/services/filter-persistence.service';

const TOGGLE_STORAGE_PAGE_ID = 'analytics-filters';

/**
 * Subset of the GA4 / Matomo / GSC sync summary the analytics page renders.
 * The backend's full payload has more fields; this interface declares only
 * what `lastSyncLabel` reads. Replaces a `: any` annotation flagged by the
 * 2026-05-09 audit (AutoIssue #21).
 */
interface SyncSummary {
  completed_at?: string | null;
  started_at?: string | null;
  rows_written?: number;
  rows_read?: number;
  status?: 'ok' | 'error' | string;
  error_message?: string;
}

interface AnalyticsToggleSnapshot {
  engagementWindowDays: 7 | 14 | 30;
  topSuggestionsOrder: 'clicks' | 'quick_exit';
}
import { EngagementMixComponent } from './engagement-mix/engagement-mix.component';
import { ImpactDiaryComponent } from './impact-diary/impact-diary.component';
import { UnderLinkedComponent } from './under-linked/under-linked.component';
import { QueryMismatchComponent } from './query-mismatch/query-mismatch.component';
import { WatchedPagesComponent } from './watched-pages/watched-pages.component';

@Component({
  selector: 'app-analytics',
  standalone: true,
  imports: [
    CommonModule, 
    MatButtonModule, 
    MatCardModule, 
    MatIconModule, 
    MatSnackBarModule, 
    MatButtonToggleModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    BaseChartDirective,
    RouterLink,
    EngagementMixComponent,
    ImpactDiaryComponent,
    UnderLinkedComponent,
    QueryMismatchComponent,
    WatchedPagesComponent,
  ],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AnalyticsComponent implements OnInit {
  private analyticsSvc = inject(AnalyticsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);
  private togglePersistence = inject(FilterPersistenceService);
  private cdr = inject(ChangeDetectorRef);

  loading = true;
  error = '';
  overview: AnalyticsOverviewResponse | null = null;
  integration: AnalyticsIntegrationResponse | null = null;
  health: AnalyticsHealthResponse | null = null;
  breakdowns: AnalyticsBreakdownsResponse | null = null;
  funnel: AnalyticsFunnelResponse | null = null;
  trend: AnalyticsTrendResponse | null = null;
  topSuggestions: AnalyticsTopSuggestionsResponse | null = null;
  versionComparison: AnalyticsVersionComparisonResponse | null = null;
  geoDetail: AnalyticsGeoDetailResponse | null = null;
  
  searchImpacts: GSCImpactSnapshot[] = [];
  loadingImpacts = false;
  selectedImpactWindow = '28d';
  expandedSuggestionId: string | null = null;
  selectedImpactDetail: SearchImpactDetailResponse | null = null;
  loadingDetail = false;

  /**
   * Phase 2 UX polish — operator-controlled window for the Engagement Mix
   * card and sort order for the Top Suggestions card. Separate from
   * selectedImpactWindow (which governs the Search Outcome section).
   */
  engagementWindowDays: 7 | 14 | 30 = 30;
  topSuggestionsOrder: 'clicks' | 'quick_exit' = 'clicks';

  scatterChartData: ChartData<'scatter'> | null = null;
  scatterChartOptions: ChartConfiguration<'scatter'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: { boxWidth: 10, usePointStyle: true, padding: 16, color: '#5f6368', font: { size: 12 } }
      },
      tooltip: {
        backgroundColor: 'rgba(32, 33, 36, 0.9)',
        titleColor: '#ffffff',
        bodyColor: '#e8eaed',
        padding: 12,
        cornerRadius: 4,
        callbacks: {
          label: (ctx) => {
            const raw = ctx.raw as { x: number; y: number; label?: string };
            const baselineClicks = $localize`:@@analytics.impact.scatter.tooltip.baseline:baseline clicks`;
            const liftLabel = $localize`:@@analytics.impact.scatter.tooltip.lift:lift`;
            return ` ${raw.label ?? ctx.dataset.label}: ${raw.x} ${baselineClicks}, ${raw.y > 0 ? '+' : ''}${raw.y}% ${liftLabel}`;
          }
        }
      }
    },
    scales: {
      x: {
        title: { 
          display: true, 
          text: $localize`:@@analytics.impact.scatter.axis.x:Baseline Traffic (Clicks)`, 
          color: '#5f6368', 
          font: { size: 11 } 
        },
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { color: 'rgba(95, 99, 104, 0.1)' }
      },
      y: {
        title: { 
          display: true, 
          text: $localize`:@@analytics.impact.scatter.axis.y:Lift (%)`, 
          color: '#5f6368', 
          font: { size: 11 } 
        },
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { color: 'rgba(95, 99, 104, 0.1)' }
      }
    }
  };

  cohortBySource: Array<{ label: string; positive: number; neutral: number; negative: number; inconclusive: number; total: number }> = [];
  cohortByAnchorFamily: Array<{ label: string; positive: number; neutral: number; negative: number; inconclusive: number; total: number }> = [];

  showFullGeo = false;
  syncingGa4 = false;
  syncingMatomo = false;
  selectedSource: 'all' | 'ga4' | 'matomo' = 'all';

  // Chart Data
  funnelChartData: ChartData<'bar'> | null = null;
  funnelChartOptions: ChartConfiguration<'bar'>['options'] = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(32, 33, 36, 0.9)',
        titleColor: '#ffffff',
        bodyColor: '#e8eaed',
        padding: 12,
        cornerRadius: 4,
        titleFont: { size: 13, weight: 'bold' },
        bodyFont: { size: 12 },
      }
    },
    scales: {
      x: { display: false, grid: { display: false } },
      y: {
        grid: { display: false },
        ticks: { color: '#5f6368', font: { size: 12 } }
      }
    }
  };

  trendChartData: ChartData<'line'> | null = null;
  trendChartOptions: ChartConfiguration<'line'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          boxWidth: 10,
          usePointStyle: true,
          padding: 20,
          color: '#5f6368',
          font: { size: 12 }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(32, 33, 36, 0.9)',
        titleColor: '#ffffff',
        bodyColor: '#e8eaed',
        padding: 12,
        cornerRadius: 4,
        titleFont: { size: 13, weight: 'bold' },
        bodyFont: { size: 12 },
      }
    },
    scales: {
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        title: { 
          display: true, 
          text: $localize`:@@analytics.engagementTrend.axis.clicks:Clicks`, 
          color: '#5f6368', 
          font: { size: 11 } 
        },
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { color: 'rgba(95, 99, 104, 0.1)' }
      },
      y1: {
        type: 'linear',
        display: true,
        position: 'right',
        title: { 
          display: true, 
          text: $localize`:@@analytics.engagementTrend.axis.rate:Rate (%)`, 
          color: '#5f6368', 
          font: { size: 11 } 
        },
        ticks: { color: '#5f6368', font: { size: 11 } },
        min: 0,
        max: 100,
        grid: { drawOnChartArea: false }
      },
      x: {
        grid: { display: false },
        ticks: { color: '#5f6368', font: { size: 11 } }
      }
    }
  };

  versionChartData: ChartData<'bar'> | null = null;
  versionChartOptions: ChartConfiguration<'bar'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: { boxWidth: 10, usePointStyle: true, padding: 16, color: '#5f6368', font: { size: 12 } }
      },
      tooltip: {
        backgroundColor: 'rgba(32, 33, 36, 0.9)',
        titleColor: '#ffffff',
        bodyColor: '#e8eaed',
        padding: 12,
        cornerRadius: 4,
      }
    },
    scales: {
      y: {
        min: 0,
        max: 100,
        title: { 
          display: true, 
          text: $localize`:@@analytics.algorithm.axis.performance:Performance (%)`, 
          color: '#5f6368', 
          font: { size: 11 } 
        },
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { color: 'rgba(95, 99, 104, 0.1)' }
      },
      x: {
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { display: false }
      }
    }
  };

  deviceChartData: ChartData<'doughnut'> | null = null;
  channelChartData: ChartData<'doughnut'> | null = null;
  geoChartData: ChartData<'bar'> | null = null;
  doughnutOptions: ChartConfiguration<'doughnut'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '68%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: { boxWidth: 10, usePointStyle: true, padding: 16, color: '#5f6368', font: { size: 12 } }
      },
      tooltip: {
        backgroundColor: 'rgba(32, 33, 36, 0.9)',
        titleColor: '#ffffff',
        bodyColor: '#e8eaed',
        padding: 12,
        cornerRadius: 4,
      }
    }
  };

  ngOnInit(): void {
    this.restoreToggleStateFromStorage();
    this.loadData();
    this.loadSearchImpacts();
  }

  /**
   * Rehydrate the engagement-window + top-suggestions-order toggles from
   * localStorage before the first data load so the restored values flow
   * straight into loadData() without a second round-trip. Validates the
   * stored values against the allowed enums so a stale or tampered
   * snapshot from an older build falls back to the component defaults.
   */
  private restoreToggleStateFromStorage(): void {
    const snapshot = this.togglePersistence.read<AnalyticsToggleSnapshot>(
      TOGGLE_STORAGE_PAGE_ID,
    );
    if (!snapshot) return;
    if (
      snapshot.engagementWindowDays === 7 ||
      snapshot.engagementWindowDays === 14 ||
      snapshot.engagementWindowDays === 30
    ) {
      this.engagementWindowDays = snapshot.engagementWindowDays;
    }
    if (
      snapshot.topSuggestionsOrder === 'clicks' ||
      snapshot.topSuggestionsOrder === 'quick_exit'
    ) {
      this.topSuggestionsOrder = snapshot.topSuggestionsOrder;
    }
  }

  private persistToggleState(): void {
    this.togglePersistence.write(TOGGLE_STORAGE_PAGE_ID, {
      engagementWindowDays: this.engagementWindowDays,
      topSuggestionsOrder: this.topSuggestionsOrder,
    });
  }

  loadSearchImpacts(): void {
    this.loadingImpacts = true;
    this.analyticsSvc.getSearchImpactList(this.selectedImpactWindow).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.searchImpacts = res.items;
        this.loadingImpacts = false;
        this.prepareScatterChart();
        this.prepareCohortData();
        this.cdr.markForCheck();
      },
      error: () => {
        this.loadingImpacts = false;
        const msg = $localize`:@@analytics.impact.error_load:Could not load Search Impact data.`;
        const dismiss = $localize`:@@analytics.impact.dismiss:Dismiss`;
        this.snack.open(msg, dismiss, { duration: 3000 });
        this.cdr.markForCheck();
      }
    });
  }

  private prepareScatterChart(): void {
    if (!this.searchImpacts.length) {
      this.scatterChartData = null;
      return;
    }

    const rewardColors: Record<string, string> = {
      positive: 'rgba(52, 168, 83, 0.85)',
      neutral: 'rgba(251, 188, 4, 0.85)',
      negative: 'rgba(234, 67, 53, 0.85)',
      inconclusive: 'rgba(128, 134, 139, 0.85)',
    };

    const groups: Record<string, Array<{ x: number; y: number; label: string }>> = {
      positive: [],
      neutral: [],
      negative: [],
      inconclusive: [],
    };

    for (const impact of this.searchImpacts) {
      groups[impact.reward_label].push({
        x: impact.baseline_clicks,
        y: parseFloat((impact.lift_clicks_pct * 100).toFixed(1)),
        label: impact.anchor_phrase,
      });
    }

    this.scatterChartData = {
      datasets: Object.entries(groups)
        .filter(([, pts]) => pts.length > 0)
        .map(([label, data]) => ({
          label: this.rewardLabel(label),
          data,
          backgroundColor: rewardColors[label],
          pointRadius: 8,
          pointHoverRadius: 11,
        }))
    };
  }

  private prepareCohortData(): void {
    type CohortRow = { label: string; positive: number; neutral: number; negative: number; inconclusive: number; total: number };

    const sourceMap: Record<string, CohortRow> = {};
    const anchorMap: Record<string, CohortRow> = {};

    const blank = (): CohortRow => ({ label: '', positive: 0, neutral: 0, negative: 0, inconclusive: 0, total: 0 });

    for (const impact of this.searchImpacts) {
      const src = impact.source_label || 'XenForo';
      if (!sourceMap[src]) { sourceMap[src] = { ...blank(), label: src }; }
      sourceMap[src][impact.reward_label]++;
      sourceMap[src].total++;

      const family = (impact.anchor_phrase?.split(' ')[0] ?? '—').toLowerCase();
      if (!anchorMap[family]) { anchorMap[family] = { ...blank(), label: family }; }
      anchorMap[family][impact.reward_label]++;
      anchorMap[family].total++;
    }

    this.cohortBySource = Object.values(sourceMap);
    this.cohortByAnchorFamily = Object.values(anchorMap)
      .sort((a, b) => b.total - a.total)
      .slice(0, 10);
  }

  onImpactWindowChange(event: MatButtonToggleChange): void {
    this.selectedImpactWindow = event.value;
    this.expandedSuggestionId = null;
    this.selectedImpactDetail = null;
    this.loadSearchImpacts();
  }

  onEngagementWindowChange(event: MatButtonToggleChange): void {
    const value = Number(event.value);
    if (value === 7 || value === 14 || value === 30) {
      this.engagementWindowDays = value;
      this.persistToggleState();
    }
    // EngagementMixComponent consumes this via an input signal and
    // re-fetches itself on change — no page-level reload needed.
  }

  onTopSuggestionsOrderChange(event: MatButtonToggleChange): void {
    if (event.value !== 'clicks' && event.value !== 'quick_exit') {
      return;
    }
    this.topSuggestionsOrder = event.value;
    this.persistToggleState();
    // Reload only the top-suggestions card rather than the whole page.
    this.analyticsSvc
      .getTopSuggestions(this.selectedSource, 30, this.topSuggestionsOrder)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.topSuggestions = response;
          this.cdr.markForCheck();
        },
        error: () => {
          // Keep the prior list visible on error; the existing global
          // error handler surfaces the failure to the operator.
          this.cdr.markForCheck();
        },
      });
  }

  toggleImpactDetails(impact: GSCImpactSnapshot): void {
    if (this.expandedSuggestionId === impact.suggestion_id) {
      this.expandedSuggestionId = null;
      this.selectedImpactDetail = null;
      return;
    }

    this.expandedSuggestionId = impact.suggestion_id;
    this.selectedImpactDetail = null;
    this.loadingDetail = true;

    this.analyticsSvc.getSearchImpactDetail(impact.suggestion_id, this.selectedImpactWindow).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.selectedImpactDetail = res;
        this.loadingDetail = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.loadingDetail = false;
        const msg = $localize`:@@analytics.impact.detail.error_load:Could not load impact details.`;
        const dismiss = $localize`:@@analytics.impact.dismiss:Dismiss`;
        this.snack.open(msg, dismiss, { duration: 3000 });
        this.cdr.markForCheck();
      }
    });
  }

  loadData(): void {
    this.loading = true;
    this.error = '';
    forkJoin({
      overview: this.analyticsSvc.getOverview(),
      integration: this.analyticsSvc.getIntegration(),
      health: this.analyticsSvc.getHealth(),
      breakdowns: this.analyticsSvc.getBreakdowns(this.selectedSource),
      funnel: this.analyticsSvc.getFunnel(this.selectedSource),
      trend: this.analyticsSvc.getTrend(this.selectedSource),
      topSuggestions: this.analyticsSvc.getTopSuggestions(
        this.selectedSource,
        30,
        this.topSuggestionsOrder,
      ),
      versionComparison: this.analyticsSvc.getTelemetryByVersion(this.selectedSource),
      geoDetail: this.analyticsSvc.getTelemetryGeoDetail(this.selectedSource),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ overview, integration, health, breakdowns, funnel, trend, topSuggestions, versionComparison, geoDetail }) => {
        this.overview = overview;
        this.integration = integration;
        this.health = health;
        this.breakdowns = breakdowns;
        this.funnel = funnel;
        this.trend = trend;
        this.topSuggestions = topSuggestions;
        this.versionComparison = versionComparison;
        this.geoDetail = geoDetail;
        
        this.prepareCharts();
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.error = $localize`:@@analytics.error_load:Could not load telemetry details.`;
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  private prepareCharts(): void {
    this.prepareFunnelChart();
    this.prepareTrendChart();
    this.prepareVersionChart();
    this.prepareBreakdownCharts();
  }

  private prepareFunnelChart(): void {
    const totals = this.funnel?.totals;
    if (!totals) return;

    this.funnelChartData = {
      labels: [
        $localize`:@@analytics.funnel.label.impressions:Impressions`, 
        $localize`:@@analytics.funnel.label.clicks:Clicks`, 
        $localize`:@@analytics.funnel.label.views:Views`, 
        $localize`:@@analytics.funnel.label.engaged:Engaged`, 
        $localize`:@@analytics.funnel.label.conversions:Conversions`
      ],
      datasets: [{
        data: [
          totals.impressions,
          totals.clicks,
          totals.destination_views,
          totals.engaged_sessions,
          totals.conversions
        ],
        backgroundColor: [
          'rgba(26, 115, 232, 0.85)',
          'rgba(26, 115, 232, 0.7)',
          'rgba(26, 115, 232, 0.55)',
          'rgba(26, 115, 232, 0.4)',
          'rgba(26, 115, 232, 0.25)',
        ],
        borderColor: '#1a73e8',
        borderWidth: 1,
        borderRadius: 4,
        barThickness: 32
      }]
    };
  }

  private prepareTrendChart(): void {
    if (!this.trend?.items.length) return;

    const labels = this.trend.items.map(i => i.date.slice(5));
    this.trendChartData = {
      labels: labels,
      datasets: [
        {
          label: $localize`:@@analytics.engagementTrend.dataset.clicks:Clicks`,
          data: this.trend.items.map(i => i.clicks),
          borderColor: '#1a73e8',
          backgroundColor: 'rgba(26, 115, 232, 0.1)',
          fill: true,
          tension: 0.4,
          yAxisID: 'y'
        },
        {
          label: $localize`:@@analytics.engagementTrend.dataset.ctr:CTR (%)`,
          data: this.trend.items.map(i => i.ctr * 100),
          borderColor: '#34a853',
          backgroundColor: 'transparent',
          borderDash: [5, 5],
          tension: 0.4,
          yAxisID: 'y1'
        },
        {
          label: $localize`:@@analytics.engagementTrend.dataset.engagement:Engagement (%)`,
          data: this.trend.items.map(i => i.engagement_rate * 100),
          borderColor: '#fbbc04',
          backgroundColor: 'transparent',
          tension: 0.4,
          yAxisID: 'y1'
        }
      ]
    };
  }

  private prepareVersionChart(): void {
    if (!this.versionComparison?.items.length) return;

    this.versionChartData = {
      labels: this.versionComparison.items.map(i => i.version_slug),
      datasets: [
        {
          label: $localize`:@@analytics.algorithm.dataset.ctr:CTR (%)`,
          data: this.versionComparison.items.map(i => i.ctr * 100),
          backgroundColor: 'rgba(26, 115, 232, 0.8)',
          borderRadius: 4
        },
        {
          label: $localize`:@@analytics.algorithm.dataset.engagement:Engagement (%)`,
          data: this.versionComparison.items.map(i => i.engagement_rate * 100),
          backgroundColor: 'rgba(52, 168, 83, 0.8)',
          borderRadius: 4
        }
      ]
    };
  }

  private prepareBreakdownCharts(): void {
    if (!this.breakdowns) return;

    // Device Doughnut
    this.deviceChartData = {
      labels: this.breakdowns.device_categories.map(i => i.label),
      datasets: [{
        data: this.breakdowns.device_categories.map(i => i.clicks),
        backgroundColor: ['#1a73e8', '#34a853', '#fbbc04', '#80868b']
      }]
    };

    // Channel Doughnut
    this.channelChartData = {
      labels: this.breakdowns.channel_groups.map(i => i.label),
      datasets: [{
        data: this.breakdowns.channel_groups.map(i => i.clicks),
        backgroundColor: ['#1a73e8', '#34a853', '#fbbc04', '#ea4335', '#fa7b17', '#80868b']
      }]
    };

    // Country Bar (Top 10)
    const topCountries = this.breakdowns.countries.slice(0, 10);
    this.geoChartData = {
      labels: topCountries.map(i => i.label),
      datasets: [{
        label: $localize`:@@analytics.geographicMix.dataset.clicks:Clicks`,
        data: topCountries.map(i => i.clicks),
        backgroundColor: 'rgba(26, 115, 232, 0.7)',
        borderRadius: 4
      }]
    };
  }

  statusLabel(status: string): string {
    return {
      connected: $localize`:@@analytics.integrations.status.connected:Connected`,
      saved: $localize`:@@analytics.integrations.status.saved:Saved`,
      error: $localize`:@@analytics.integrations.status.error:Error`,
      not_configured: $localize`:@@analytics.integrations.status.not_configured:Not set up`,
    }[status] ?? $localize`:@@analytics.integrations.status.unknown:Unknown`;
  }

  ga4StatusLabel(): string {
    const ga4 = this.overview?.ga4;
    return this.statusLabel(ga4?.read_connection_status || ga4?.connection_status || 'not_configured');
  }

  ga4StatusMessage(): string {
    const ga4 = this.overview?.ga4;
    return ga4?.read_connection_message || ga4?.connection_message || $localize`:@@analytics.integrations.ga4.setup_hint:Fill in the GA4 fields and test the connection.`;
  }

  lastSyncLabel(sync: SyncSummary | null | undefined): string {
    if (!sync) return $localize`:@@analytics.integrations.sync.never:Never synced`;
    const stamp = sync.completed_at || sync.started_at;
    if (!stamp) {
      const rows = sync.rows_written || 0;
      return $localize`:@@analytics.integrations.sync.rows_only:${rows} rows written`;
    }

    let summary = `${new Date(stamp).toLocaleString()}`;
    if (sync.rows_written !== undefined) {
      const written = sync.rows_written;
      summary += $localize`:@@analytics.integrations.sync.written: - ${written} rows written`;
    }
    if (sync.rows_read !== undefined && sync.rows_read > 0) {
      const readCount = sync.rows_read;
      summary += $localize`:@@analytics.integrations.sync.read: (${readCount} read)`;
    }
    if (sync.status === 'error') {
      const err = sync.error_message || $localize`:@@analytics.integrations.sync.unknown_error:Unknown`;
      summary += $localize`:@@analytics.integrations.sync.failed: [FAILED: ${err}]`;
    }

    return summary;
  }

  integrationStatusLabel(status: AnalyticsIntegrationResponse['status'] | undefined): string {
    return status === 'ready' 
      ? $localize`:@@analytics.integrations.status.ready:Ready to install` 
      : $localize`:@@analytics.integrations.status.needs_setup:Needs setup`;
  }

  sourceLabel(source: 'all' | 'ga4' | 'matomo'): string {
    return {
      all: $localize`:@@analytics.source.combined_label:Combined`,
      ga4: $localize`:@@analytics.source.ga4_label:GA4 only`,
      matomo: $localize`:@@analytics.source.matomo_label:Matomo only`,
    }[source];
  }

  onSourceChange(event: MatButtonToggleChange): void {
    this.chooseSource(event.value);
  }

  chooseSource(source: 'all' | 'ga4' | 'matomo'): void {
    if (this.selectedSource === source) {
      return;
    }
    this.selectedSource = source;
    this.loadData();
  }

  formatPercent(value: number): string {
    return `${(value * 100).toFixed(1)}%`;
  }

  /**
   * Phase 2c — operator warning threshold: a quick-exit rate at or above this
   * value gets a red tint in the top-suggestions table so bad-match rows are
   * easy to spot. 20% chosen as a conservative working threshold — not a
   * ranker input, purely a UI cue.
   */
  private readonly HIGH_QUICK_EXIT_RATE = 0.2;

  isHighQuickExit(item: AnalyticsTopSuggestion): boolean {
    return item.quick_exit_rate >= this.HIGH_QUICK_EXIT_RATE;
  }

  quickExitTooltip(item: AnalyticsTopSuggestion): string {
    if (item.destination_views === 0) {
      return $localize`:@@analytics.topSuggestions.tooltip.no_views:No destination views yet in this window.`;
    }
    const pct = (item.quick_exit_rate * 100).toFixed(1);
    const sessions = item.quick_exit_sessions;
    const views = item.destination_views;
    
    return $localize`:@@analytics.topSuggestions.tooltip.quick_exit_desc:${sessions} of ${views} readers (${pct}%) left within 5 seconds of landing on the destination. High quick-exit usually means the link does not match reader intent.`;
  }

  coverageStateLabel(state: AnalyticsHealthSummary['latest_state']): string {
    return {
      healthy: $localize`:@@analytics.systemHealth.state.healthy:Healthy`,
      partial: $localize`:@@analytics.systemHealth.state.partial:Partial`,
      degraded: $localize`:@@analytics.systemHealth.state.degraded:Degraded`,
      no_data: $localize`:@@analytics.systemHealth.state.no_data:No data`,
    }[state];
  }

  coverageStateClass(state: AnalyticsHealthSummary['latest_state']): string {
    return `status-badge--${state}`;
  }

  toggleFullGeo(): void {
    this.showFullGeo = !this.showFullGeo;
  }

  calculateUplift(row: AnalyticsVersionComparisonRow): string {
    // Basic uplift calculation vs the average of others
    if (!this.versionComparison || this.versionComparison.items.length < 2) return '';
    const others = this.versionComparison.items.filter(i => i.version_slug !== row.version_slug);
    const avgCtr = others.reduce((acc, i) => acc + i.ctr, 0) / others.length;
    if (avgCtr === 0) return '';
    const uplift = ((row.ctr - avgCtr) / avgCtr) * 100;
    const sign = uplift >= 0 ? '+' : '';
    return `${sign}${uplift.toFixed(1)}%`;
  }

  sourceName(source: string): string {
    if (source === 'ga4') return 'GA4';
    if (source === 'matomo') return 'Matomo';
    if (source === 'unknown') return 'Unknown';
    return source;
  }

  metricLabel(value: number, suffix: string): string {
    return `${value} ${suffix}`;
  }

  breakdownBarWidth(value: number, rows: Array<{ clicks: number }>): string {
    const max = Math.max(...rows.map((row) => row.clicks), 0);
    if (!max) {
      return '0%';
    }
    return `${Math.max((value / max) * 100, 8)}%`;
  }

  funnelSteps(): Array<{ label: string; value: number }> {
    const totals = this.funnel?.totals;
    if (!totals) {
      return [];
    }
    return [
      { label: $localize`:@@analytics.funnel.step.impressions:Impressions`, value: totals.impressions },
      { label: $localize`:@@analytics.funnel.step.clicks:Clicks`, value: totals.clicks },
      { label: $localize`:@@analytics.funnel.step.views:Destination views`, value: totals.destination_views },
      { label: $localize`:@@analytics.funnel.step.engaged:Engaged sessions`, value: totals.engaged_sessions },
      { label: $localize`:@@analytics.funnel.step.conversions:Conversions`, value: totals.conversions },
    ];
  }

  funnelBarWidth(value: number): string {
    const max = Math.max(...this.funnelSteps().map((step) => step.value), 0);
    if (!max) {
      return '0%';
    }
    return `${Math.max((value / max) * 100, 6)}%`;
  }

  trendClickHeight(point: AnalyticsTrendPoint): string {
    const max = Math.max(...(this.trend?.items ?? []).map((item) => item.clicks), 0);
    if (!max) {
      return '8%';
    }
    return `${Math.max((point.clicks / max) * 100, 8)}%`;
  }

  async copySnippet(): Promise<void> {
    const snippet = this.integration?.browser_snippet ?? '';
    if (!snippet) {
      const msg = $localize`:@@analytics.integrations.copy.error_no_snippet:No browser snippet is ready yet.`;
      const dismiss = $localize`:@@analytics.impact.dismiss:Dismiss`;
      this.snack.open(msg, dismiss, { duration: 3000 });
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(snippet);
        const msg = $localize`:@@analytics.integrations.copy.success:Browser snippet copied.`;
        this.snack.open(msg, undefined, { duration: 2500 });
        return;
      }
    } catch {
      // Fall through to the plain warning below.
    }
    const msg = $localize`:@@analytics.integrations.copy.error_clipboard:Clipboard copy is not available in this browser.`;
    const dismiss = $localize`:@@analytics.impact.dismiss:Dismiss`;
    this.snack.open(msg, dismiss, { duration: 3500 });
  }

  runGa4Sync(): void {
    this.syncingGa4 = true;
    this.analyticsSvc.runGa4Sync().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        this.syncingGa4 = false;
        this.snack.open(response.message, undefined, { duration: 3000 });
        this.loadData();
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.syncingGa4 = false;
        const msg = error?.error?.detail || $localize`:@@analytics.integrations.ga4.error_sync:Could not queue the GA4 sync.`;
        const dismiss = $localize`:@@analytics.impact.dismiss:Dismiss`;
        this.snack.open(msg, dismiss, { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  runMatomoSync(): void {
    this.syncingMatomo = true;
    this.analyticsSvc.runMatomoSync().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        this.syncingMatomo = false;
        this.snack.open(response.message, undefined, { duration: 3000 });
        this.loadData();
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.syncingMatomo = false;
        const msg = error?.error?.detail || $localize`:@@analytics.integrations.matomo.error_sync:Could not queue the Matomo sync.`;
        const dismiss = $localize`:@@analytics.impact.dismiss:Dismiss`;
        this.snack.open(msg, dismiss, { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  rewardLabel(label: string): string {
    return {
      positive: $localize`:@@analytics.impact.reward.positive:Positive Uplift`,
      neutral: $localize`:@@analytics.impact.reward.neutral:Neutral Change`,
      negative: $localize`:@@analytics.impact.reward.negative:Negative Impact`,
      inconclusive: $localize`:@@analytics.impact.reward.inconclusive:Inconclusive`,
    }[label] ?? label;
  }

  rewardClass(label: string): string {
    return `reward-badge--${label}`;
  }
}
