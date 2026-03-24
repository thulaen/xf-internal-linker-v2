import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SuggestionCounts {
  pending: number;
  approved: number;
  rejected: number;
  applied: number;
  total: number;
}

export interface PipelineRunSummary {
  run_id: string;
  run_state: string;
  rerun_mode: string;
  suggestions_created: number;
  destinations_processed: number;
  duration_display: string | null;
  created_at: string;
}

export interface ImportJobSummary {
  job_id: string;
  status: string;
  source: string;
  mode: string;
  items_synced: number;
  created_at: string;
  completed_at: string | null;
}

export interface LastSync {
  completed_at: string;
  source: string;
  mode: string;
  items_synced: number;
}

export interface DashboardData {
  suggestion_counts: SuggestionCounts;
  content_count: number;
  last_sync: LastSync | null;
  pipeline_runs: PipelineRunSummary[];
  recent_imports: ImportJobSummary[];
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private http = inject(HttpClient);
  private url = '/api/dashboard/';

  get(): Observable<DashboardData> {
    return this.http.get<DashboardData>(this.url);
  }
}
