import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { forkJoin } from 'rxjs';
import {
  AnalyticsBreakdownsResponse,
  AnalyticsFunnelResponse,
  AnalyticsHealthResponse,
  AnalyticsHealthSummary,
  AnalyticsIntegrationResponse,
  AnalyticsOverviewResponse,
  AnalyticsService,
  AnalyticsTopSuggestionsResponse,
  AnalyticsTrendPoint,
  AnalyticsTrendResponse,
} from './analytics.service';

@Component({
  selector: 'app-analytics',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatCardModule, MatIconModule, MatSnackBarModule],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.scss'],
})
export class AnalyticsComponent implements OnInit {
  private analyticsSvc = inject(AnalyticsService);
  private snack = inject(MatSnackBar);

  loading = true;
  error = '';
  overview: AnalyticsOverviewResponse | null = null;
  integration: AnalyticsIntegrationResponse | null = null;
  health: AnalyticsHealthResponse | null = null;
  breakdowns: AnalyticsBreakdownsResponse | null = null;
  funnel: AnalyticsFunnelResponse | null = null;
  trend: AnalyticsTrendResponse | null = null;
  topSuggestions: AnalyticsTopSuggestionsResponse | null = null;
  syncingGa4 = false;
  syncingMatomo = false;
  selectedSource: 'all' | 'ga4' | 'matomo' = 'all';

  ngOnInit(): void {
    this.loadData();
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
    }).subscribe({
      next: ({ overview, integration, health, breakdowns, funnel, trend, topSuggestions }) => {
        this.overview = overview;
        this.integration = integration;
        this.health = health;
        this.breakdowns = breakdowns;
        this.funnel = funnel;
        this.trend = trend;
        this.topSuggestions = topSuggestions;
        this.loading = false;
      },
      error: () => {
        this.error = 'Could not load telemetry details.';
        this.loading = false;
      },
    });
  }

  statusLabel(status: string): string {
    return {
      connected: 'Connected',
      saved: 'Saved',
      error: 'Error',
      not_configured: 'Not set up',
    }[status] ?? 'Unknown';
  }

  lastSyncLabel(sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null): string {
    if (!sync) return 'Never synced';
    const stamp = sync.completed_at || sync.started_at;
    if (!stamp) return `${sync.rows_written} rows written`;
    return `${new Date(stamp).toLocaleString()} - ${sync.rows_written} rows written`;
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

  sourceName(source: string): string {
    if (source === 'ga4') return 'GA4';
    if (source === 'matomo') return 'Matomo';
    if (source === 'unknown') return 'Unknown';
    return source;
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
    this.analyticsSvc.runGa4Sync().subscribe({
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
    this.analyticsSvc.runMatomoSync().subscribe({
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
}
