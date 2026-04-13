import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap, of, shareReplay, finalize } from 'rxjs';

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
  open_broken_links: number;
  last_sync: LastSync | null;
  pipeline_runs: PipelineRunSummary[];
  recent_imports: ImportJobSummary[];
  system_health: {
    status: 'healthy' | 'warning' | 'error' | 'down' | 'stale';
    summary: { [key: string]: number };
    total_monitored: number;
  };
  // Freshness ribbon fields (nullable until backend endpoints exist)
  last_sync_at?: string | null;
  last_analytics_at?: string | null;
  last_pipeline_at?: string | null;
  runtime_mode?: string;
}

/** Cache lives for 60 seconds before a fresh fetch is required. */
const CACHE_TTL_MS = 60_000;

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private http = inject(HttpClient);
  private url = '/api/dashboard/';
  private dataSubject = new BehaviorSubject<DashboardData | null>(null);
  readonly data$ = this.dataSubject.asObservable();
  private refreshRequest: Observable<DashboardData> | null = null;
  private lastFetchedAt = 0;

  get(): Observable<DashboardData> {
    const current = this.dataSubject.value;
    const cacheValid = current && (Date.now() - this.lastFetchedAt < CACHE_TTL_MS);
    if (cacheValid && !this.refreshRequest) {
      return of(current);
    }
    return this.refresh();
  }

  refresh(): Observable<DashboardData> {
    if (this.refreshRequest) {
      return this.refreshRequest;
    }

    const request = this.http.get<DashboardData>(this.url).pipe(
      tap((data) => {
        this.dataSubject.next(data);
        this.lastFetchedAt = Date.now();
      }),
      shareReplay(1),
      finalize(() => {
        if (this.refreshRequest === request) {
          this.refreshRequest = null;
        }
      })
    );

    this.refreshRequest = request;
    return request;
  }

  /** Clear cache so the next get() forces a fresh fetch. */
  invalidate(): void {
    this.lastFetchedAt = 0;
  }

  updateOpenBrokenLinks(count: number): void {
    const current = this.dataSubject.value;
    if (!current) {
      return;
    }

    this.dataSubject.next({
      ...current,
      open_broken_links: count,
    });
  }
}
