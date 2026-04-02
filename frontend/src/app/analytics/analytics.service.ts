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

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private http = inject(HttpClient);

  getOverview(): Observable<AnalyticsOverviewResponse> {
    return this.http.get<AnalyticsOverviewResponse>('/api/analytics/telemetry/overview/');
  }
}
