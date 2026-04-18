import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';

export interface AnalyticsOverviewResponse {
  ga4: {
    connection_status: string;
    connection_message: string;
    read_connection_status?: string;
    read_connection_message?: string;
    last_sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null;
  };
  matomo: {
    connection_status: string;
    connection_message: string;
    last_sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null;
  };
  totals_last_30_days: {
    impressions: number;
    clicks: number;
    destination_views: number;
    engaged_sessions: number;
    conversions: number;
  };
  telemetry_row_count: number;
  coverage_row_count: number;
  latest_coverage: {
    date: string;
    coverage_state: string;
    expected_instrumented_links: number;
    observed_impression_links: number;
    observed_click_links: number;
  } | null;
}

export interface AnalyticsIntegrationResponse {
  status: 'ready' | 'needs_settings';
  message: string;
  event_schema: string;
  ga4_browser_ready: boolean;
  matomo_browser_ready: boolean;
  session_ttl_minutes: number;
  install_steps: string[];
  browser_snippet: string;
}

/**
 * Phase 2b — engagement mix for the selected source and time window. Surfaces
 * the three new SuggestionTelemetryDaily columns (quick_exit, dwell_30s,
 * dwell_60s) alongside destination_views and engaged_sessions. Rates are
 * independent tier-reach percentages (cumulative events), not stacked shares.
 * See backend/apps/analytics/views.py::AnalyticsTelemetryEngagementMixView.
 */
export interface AnalyticsEngagementMixResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  totals: {
    destination_views: number;
    engaged_sessions: number;
    quick_exit_sessions: number;
    dwell_30s_sessions: number;
    dwell_60s_sessions: number;
  };
  rates: {
    quick_exit_rate: number;
    engaged_rate: number;
    dwell_30s_rate: number;
    dwell_60s_rate: number;
  };
}

export interface AnalyticsFunnelResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  totals: {
    impressions: number;
    clicks: number;
    destination_views: number;
    engaged_sessions: number;
    conversions: number;
  };
  by_source: Array<{
    telemetry_source: 'ga4' | 'matomo';
    impressions: number;
    clicks: number;
    destination_views: number;
    engaged_sessions: number;
    conversions: number;
  }>;
}

export interface AnalyticsTrendPoint {
  date: string;
  impressions: number;
  clicks: number;
  destination_views: number;
  engaged_sessions: number;
  conversions: number;
  ctr: number;
  engagement_rate: number;
}

export interface AnalyticsTrendResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  items: AnalyticsTrendPoint[];
}

export interface AnalyticsTopSuggestion {
  suggestion_id: string;
  telemetry_source: 'ga4' | 'matomo';
  destination_title: string;
  anchor_phrase: string;
  status: string;
  impressions: number;
  clicks: number;
  destination_views: number;
  engaged_sessions: number;
  conversions: number;
  // Phase 2c — per-suggestion engagement drill-down. High quick_exit_rate
  // flags bad-match rows; high dwell_60s_rate flags standout good-match rows.
  quick_exit_sessions: number;
  dwell_60s_sessions: number;
  ctr: number;
  engagement_rate: number;
  quick_exit_rate: number;
  dwell_60s_rate: number;
}

export interface AnalyticsTopSuggestionsResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  items: AnalyticsTopSuggestion[];
}

export interface AnalyticsHealthSummary {
  row_count: number;
  latest_state: 'healthy' | 'partial' | 'degraded' | 'no_data';
  latest_date: string | null;
  event_schema: string;
  healthy_days: number;
  partial_days: number;
  degraded_days: number;
  expected_instrumented_links: number;
  observed_impression_links: number;
  observed_click_links: number;
  attributed_destination_sessions: number;
  unattributed_destination_sessions: number;
  duplicate_event_drops: number;
  missing_metadata_events: number;
  delayed_rows_rewritten: number;
  impression_coverage_rate: number;
  click_coverage_rate: number;
  attribution_rate: number;
}

export interface AnalyticsHealthResponse {
  days: number;
  overall: AnalyticsHealthSummary;
  sources: Array<AnalyticsHealthSummary & { source_label: string }>;
}

export interface AnalyticsBreakdownRow {
  label: string;
  impressions: number;
  clicks: number;
  engaged_sessions: number;
  ctr: number;
}

export interface AnalyticsBreakdownsResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  device_categories: AnalyticsBreakdownRow[];
  channel_groups: AnalyticsBreakdownRow[];
  countries: AnalyticsBreakdownRow[];
}

export interface AnalyticsVersionComparisonRow {
  version_slug: string;
  impressions: number;
  clicks: number;
  destination_views: number;
  engaged_sessions: number;
  conversions: number;
  ctr: number;
  engagement_rate: number;
  conversion_rate: number;
}

export interface AnalyticsVersionComparisonResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  items: AnalyticsVersionComparisonRow[];
}

export interface AnalyticsGeoDetailRow {
  country: string;
  region: string;
  impressions: number;
  clicks: number;
  engaged_sessions: number;
  conversions: number;
  ctr: number;
}

export interface AnalyticsGeoDetailResponse {
  days: number;
  selected_source: 'all' | 'ga4' | 'matomo';
  items: AnalyticsGeoDetailRow[];
}

export interface AnalyticsSyncTriggerResponse {
  sync_run_id: number;
  task_id: string;
  source: 'ga4' | 'matomo';
  status: string;
  message: string;
}

export interface GSCImpactSnapshot {
  suggestion_id: string;
  anchor_phrase: string;
  destination_title: string;
  status: string;
  apply_date: string;
  window_type: string;
  baseline_clicks: number;
  post_clicks: number;
  lift_clicks_pct: number;
  lift_clicks_absolute: number;
  probability_of_uplift: number;
  reward_label: 'positive' | 'neutral' | 'negative' | 'inconclusive';
  last_computed_at: string;
  source_type: 'xenforo' | 'wordpress';
  source_label: string;
}

export interface GSCKeywordImpact {
  query: string;
  clicks_baseline: number;
  clicks_post: number;
  impressions_baseline: number;
  impressions_post: number;
  lift_percent: number;
  is_anchor_match: boolean;
}

export interface ImpactReport {
  metric_type: string;
  before_value: number;
  after_value: number;
  before_date_range: { start: string; end: string };
  after_date_range: { start: string; end: string };
  delta_percent: number;
  control_pool_size: number;
  control_match_count: number;
  control_match_quality: number | null;
  is_conclusive: boolean;
  created_at: string;
}

export interface SearchImpactDetailResponse {
  suggestion_id: string;
  anchor_phrase: string;
  destination_title: string;
  applied_at: string;
  impact: GSCImpactSnapshot | null;
  keywords: GSCKeywordImpact[];
  impact_reports: ImpactReport[];
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private http = inject(HttpClient);

  getOverview(): Observable<AnalyticsOverviewResponse> {
    return this.http.get<AnalyticsOverviewResponse>('/api/analytics/telemetry/overview/').pipe(catchError((err) => throwError(() => err)));
  }

  getIntegration(): Observable<AnalyticsIntegrationResponse> {
    return this.http.get<AnalyticsIntegrationResponse>('/api/analytics/telemetry/integration/').pipe(catchError((err) => throwError(() => err)));
  }

  getFunnel(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsFunnelResponse> {
    return this.http.get<AnalyticsFunnelResponse>(`/api/analytics/telemetry/funnel/?source=${source}&days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  getEngagementMix(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsEngagementMixResponse> {
    return this.http.get<AnalyticsEngagementMixResponse>(`/api/analytics/telemetry/engagement-mix/?source=${source}&days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  getTrend(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsTrendResponse> {
    return this.http.get<AnalyticsTrendResponse>(`/api/analytics/telemetry/trend/?source=${source}&days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  getTopSuggestions(
    source: 'all' | 'ga4' | 'matomo' = 'all',
    days = 30,
    order: 'clicks' | 'quick_exit' = 'clicks',
  ): Observable<AnalyticsTopSuggestionsResponse> {
    return this.http
      .get<AnalyticsTopSuggestionsResponse>(
        `/api/analytics/telemetry/top-suggestions/?source=${source}&days=${days}&order=${order}`,
      )
      .pipe(catchError((err) => throwError(() => err)));
  }

  getHealth(days = 30): Observable<AnalyticsHealthResponse> {
    return this.http.get<AnalyticsHealthResponse>(`/api/analytics/telemetry/health/?days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  getBreakdowns(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsBreakdownsResponse> {
    return this.http.get<AnalyticsBreakdownsResponse>(`/api/analytics/telemetry/breakdowns/?source=${source}&days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  getTelemetryByVersion(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsVersionComparisonResponse> {
    return this.http.get<AnalyticsVersionComparisonResponse>(`/api/analytics/telemetry/by-version/?source=${source}&days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  getTelemetryGeoDetail(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsGeoDetailResponse> {
    return this.http.get<AnalyticsGeoDetailResponse>(`/api/analytics/telemetry/geo-detail/?source=${source}&days=${days}`).pipe(catchError((err) => throwError(() => err)));
  }

  runGa4Sync(): Observable<AnalyticsSyncTriggerResponse> {
    return this.http.post<AnalyticsSyncTriggerResponse>('/api/analytics/telemetry/ga4-sync/', {}).pipe(catchError((err) => throwError(() => err)));
  }

  runMatomoSync(): Observable<AnalyticsSyncTriggerResponse> {
    return this.http.post<AnalyticsSyncTriggerResponse>('/api/analytics/telemetry/matomo-sync/', {}).pipe(catchError((err) => throwError(() => err)));
  }

  getSearchImpactList(window = '28d'): Observable<{ items: GSCImpactSnapshot[] }> {
    return this.http.get<{ items: GSCImpactSnapshot[] }>(`/api/analytics/search-impact/?window=${window}`).pipe(catchError((err) => throwError(() => err)));
  }

  getSearchImpactDetail(suggestionId: string, window = '28d'): Observable<SearchImpactDetailResponse> {
    return this.http.get<SearchImpactDetailResponse>(`/api/analytics/search-impact/${suggestionId}/?window=${window}`).pipe(catchError((err) => throwError(() => err)));
  }
}
