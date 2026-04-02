import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface AnalyticsOverviewResponse {
  ga4: {
    connection_status: string;
    connection_message: string;
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

export interface AnalyticsSyncTriggerResponse {
  sync_run_id: number;
  task_id: string;
  source: 'ga4' | 'matomo';
  status: string;
  message: string;
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

  runGa4Sync(): Observable<AnalyticsSyncTriggerResponse> {
    return this.http.post<AnalyticsSyncTriggerResponse>('/api/analytics/telemetry/ga4-sync/', {});
  }

  runMatomoSync(): Observable<AnalyticsSyncTriggerResponse> {
    return this.http.post<AnalyticsSyncTriggerResponse>('/api/analytics/telemetry/matomo-sync/', {});
  }
}
