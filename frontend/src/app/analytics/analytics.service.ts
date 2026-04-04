import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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
  ctr: number;
  engagement_rate: number;
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

export interface SearchImpactDetailResponse {
  suggestion_id: string;
  anchor_phrase: string;
  destination_title: string;
  applied_at: string;
  impact: GSCImpactSnapshot | null;
  keywords: GSCKeywordImpact[];
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private http = inject(HttpClient);

  getOverview(): Observable<AnalyticsOverviewResponse> {
    return this.http.get<AnalyticsOverviewResponse>('/api/analytics/telemetry/overview/');
  }

  getIntegration(): Observable<AnalyticsIntegrationResponse> {
    return this.http.get<AnalyticsIntegrationResponse>('/api/analytics/telemetry/integration/');
  }

  getFunnel(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsFunnelResponse> {
    return this.http.get<AnalyticsFunnelResponse>(`/api/analytics/telemetry/funnel/?source=${source}&days=${days}`);
  }

  getTrend(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsTrendResponse> {
    return this.http.get<AnalyticsTrendResponse>(`/api/analytics/telemetry/trend/?source=${source}&days=${days}`);
  }

  getTopSuggestions(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsTopSuggestionsResponse> {
    return this.http.get<AnalyticsTopSuggestionsResponse>(`/api/analytics/telemetry/top-suggestions/?source=${source}&days=${days}`);
  }

  getHealth(days = 30): Observable<AnalyticsHealthResponse> {
    return this.http.get<AnalyticsHealthResponse>(`/api/analytics/telemetry/health/?days=${days}`);
  }

  getBreakdowns(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsBreakdownsResponse> {
    return this.http.get<AnalyticsBreakdownsResponse>(`/api/analytics/telemetry/breakdowns/?source=${source}&days=${days}`);
  }

  getTelemetryByVersion(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsVersionComparisonResponse> {
    return this.http.get<AnalyticsVersionComparisonResponse>(`/api/analytics/telemetry/by-version/?source=${source}&days=${days}`);
  }

  getTelemetryGeoDetail(source: 'all' | 'ga4' | 'matomo' = 'all', days = 30): Observable<AnalyticsGeoDetailResponse> {
    return this.http.get<AnalyticsGeoDetailResponse>(`/api/analytics/telemetry/geo-detail/?source=${source}&days=${days}`);
  }

  runGa4Sync(): Observable<AnalyticsSyncTriggerResponse> {
    return this.http.post<AnalyticsSyncTriggerResponse>('/api/analytics/telemetry/ga4-sync/', {});
  }

  runMatomoSync(): Observable<AnalyticsSyncTriggerResponse> {
    return this.http.post<AnalyticsSyncTriggerResponse>('/api/analytics/telemetry/matomo-sync/', {});
  }

  getSearchImpactList(window = '28d'): Observable<{ items: GSCImpactSnapshot[] }> {
    return this.http.get<{ items: GSCImpactSnapshot[] }>(`/api/analytics/search-impact/?window=${window}`);
  }

  getSearchImpactDetail(suggestionId: string, window = '28d'): Observable<SearchImpactDetailResponse> {
    return this.http.get<SearchImpactDetailResponse>(`/api/analytics/search-impact/${suggestionId}/?window=${window}`);
  }
}
