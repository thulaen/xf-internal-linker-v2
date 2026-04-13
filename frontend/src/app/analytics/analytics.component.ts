import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, DestroyRef } from '@angular/core';
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
  AnalyticsTopSuggestionsResponse,
  AnalyticsTrendPoint,
  AnalyticsTrendResponse,
  AnalyticsVersionComparisonResponse,
  AnalyticsVersionComparisonRow,
  GSCImpactSnapshot,
  SearchImpactDetailResponse,
} from './analytics.service';
import { ImpactDiaryComponent } from './impact-diary/impact-diary.component';
import { UnderLinkedComponent } from './under-linked/under-linked.component';
import { QueryMismatchComponent } from './query-mismatch/query-mismatch.component';
import { WatchedPagesComponent } from './watched-pages/watched-pages.component';
import { TrafficWorkbenchComponent } from './traffic-workbench/traffic-workbench.component';

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
    ImpactDiaryComponent,
    UnderLinkedComponent,
    QueryMismatchComponent,
    WatchedPagesComponent,
    TrafficWorkbenchComponent,
  ],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.scss'],
})
export class AnalyticsComponent implements OnInit {
  private analyticsSvc = inject(AnalyticsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

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
            return ` ${raw.label ?? ctx.dataset.label}: ${raw.x} baseline clicks, ${raw.y > 0 ? '+' : ''}${raw.y}% lift`;
          }
        }
      }
    },
    scales: {
      x: {
        title: { display: true, text: 'Baseline Traffic (Clicks)', color: '#5f6368', font: { size: 11 } },
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { color: 'rgba(95, 99, 104, 0.1)' }
      },
      y: {
        title: { display: true, text: 'Lift (%)', color: '#5f6368', font: { size: 11 } },
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
        title: { display: true, text: 'Clicks', color: '#5f6368', font: { size: 11 } },
        ticks: { color: '#5f6368', font: { size: 11 } },
        grid: { color: 'rgba(95, 99, 104, 0.1)' }
      },
      y1: {
        type: 'linear',
        display: true,
        position: 'right',
        title: { display: true, text: 'Rate (%)', color: '#5f6368', font: { size: 11 } },
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
        title: { display: true, text: 'Performance (%)', color: '#5f6368', font: { size: 11 } },
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
    this.loadData();
    this.loadSearchImpacts();
  }

  loadSearchImpacts(): void {
    this.loadingImpacts = true;
    this.analyticsSvc.getSearchImpactList(this.selectedImpactWindow).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.searchImpacts = res.items;
        this.loadingImpacts = false;
        this.prepareScatterChart();
        this.prepareCohortData();
      },
      error: () => {
        this.loadingImpacts = false;
        this.snack.open('Could not load Search Impact data.', 'Dismiss', { duration: 3000 });
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
      },
      error: () => {
        this.loadingDetail = false;
        this.snack.open('Could not load impact details.', 'Dismiss', { duration: 3000 });
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
      topSuggestions: this.analyticsSvc.getTopSuggestions(this.selectedSource),
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
      },
      error: () => {
        this.error = 'Could not load telemetry details.';
        this.loading = false;
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
      labels: ['Impressions', 'Clicks', 'Views', 'Engaged', 'Conversions'],
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
          label: 'Clicks',
          data: this.trend.items.map(i => i.clicks),
          borderColor: '#1a73e8',
          backgroundColor: 'rgba(26, 115, 232, 0.1)',
          fill: true,
          tension: 0.4,
          yAxisID: 'y'
        },
        {
          label: 'CTR (%)',
          data: this.trend.items.map(i => i.ctr * 100),
          borderColor: '#34a853',
          backgroundColor: 'transparent',
          borderDash: [5, 5],
          tension: 0.4,
          yAxisID: 'y1'
        },
        {
          label: 'Engagement (%)',
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
          label: 'CTR (%)',
          data: this.versionComparison.items.map(i => i.ctr * 100),
          backgroundColor: 'rgba(26, 115, 232, 0.8)',
          borderRadius: 4
        },
        {
          label: 'Engagement (%)',
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
        label: 'Clicks',
        data: topCountries.map(i => i.clicks),
        backgroundColor: 'rgba(26, 115, 232, 0.7)',
        borderRadius: 4
      }]
    };
  }

  statusLabel(status: string): string {
    return {
      connected: 'Connected',
      saved: 'Saved',
      error: 'Error',
      not_configured: 'Not set up',
    }[status] ?? 'Unknown';
  }

  ga4StatusLabel(): string {
    const ga4 = this.overview?.ga4;
    return this.statusLabel(ga4?.read_connection_status || ga4?.connection_status || 'not_configured');
  }

  ga4StatusMessage(): string {
    const ga4 = this.overview?.ga4;
    return ga4?.read_connection_message || ga4?.connection_message || 'Fill in the GA4 fields and test the connection.';
  }

  lastSyncLabel(sync: any | null): string {
    if (!sync) return 'Never synced';
    const stamp = sync.completed_at || sync.started_at;
    if (!stamp) return `${sync.rows_written || 0} rows written`;
    
    let summary = `${new Date(stamp).toLocaleString()}`;
    if (sync.rows_written !== undefined) summary += ` - ${sync.rows_written} rows written`;
    if (sync.rows_read !== undefined && sync.rows_read > 0) summary += ` (${sync.rows_read} read)`;
    if (sync.status && sync.status === 'error') summary += ` [FAILED: ${sync.error_message || 'Unknown'}]`;
    
    return summary;
  }

  integrationStatusLabel(status: AnalyticsIntegrationResponse['status'] | undefined): string {
    return status === 'ready' ? 'Ready to install' : 'Needs setup';
  }

  sourceLabel(source: 'all' | 'ga4' | 'matomo'): string {
    return {
      all: 'Combined',
      ga4: 'GA4 only',
      matomo: 'Matomo only',
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

  coverageStateLabel(state: AnalyticsHealthSummary['latest_state']): string {
    return {
      healthy: 'Healthy',
      partial: 'Partial',
      degraded: 'Degraded',
      no_data: 'No data',
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
      { label: 'Impressions', value: totals.impressions },
      { label: 'Clicks', value: totals.clicks },
      { label: 'Destination views', value: totals.destination_views },
      { label: 'Engaged sessions', value: totals.engaged_sessions },
      { label: 'Conversions', value: totals.conversions },
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
      this.snack.open('No browser snippet is ready yet.', 'Dismiss', { duration: 3000 });
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(snippet);
        this.snack.open('Browser snippet copied.', undefined, { duration: 2500 });
        return;
      }
    } catch {
      // Fall through to the plain warning below.
    }
    this.snack.open('Clipboard copy is not available in this browser.', 'Dismiss', { duration: 3500 });
  }

  runGa4Sync(): void {
    this.syncingGa4 = true;
    this.analyticsSvc.runGa4Sync().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        this.syncingGa4 = false;
        this.snack.open(response.message, undefined, { duration: 3000 });
        this.loadData();
      },
      error: (error) => {
        this.syncingGa4 = false;
        this.snack.open(error?.error?.detail || 'Could not queue the GA4 sync.', 'Dismiss', { duration: 4000 });
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
      },
      error: (error) => {
        this.syncingMatomo = false;
        this.snack.open(error?.error?.detail || 'Could not queue the Matomo sync.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  rewardLabel(label: string): string {
    return {
      positive: 'Positive Uplift',
      neutral: 'Neutral Change',
      negative: 'Negative Impact',
      inconclusive: 'Inconclusive',
    }[label] ?? label;
  }

  rewardClass(label: string): string {
    return `reward-badge--${label}`;
  }
}
