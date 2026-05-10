import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

export type ConfigTier = 'required_to_run' | 'required_for_sync' | 'required_for_analytics' | 'optional';

export interface ServiceHealth {
  service_key: string;
  service_name: string;
  service_description: string;
  status: 'healthy' | 'warning' | 'error' | 'down' | 'stale' | 'not_configured' | 'not_enabled';
  status_label: string;
  config_tier: ConfigTier;
  last_check_at: string;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_message: string;
  issue_description: string;
  suggested_fix: string;
  // Per-service detail blob with all the fields the health template
  // currently reads. Each field is optional because the schema varies
  // per service. Replaces a `: any` annotation flagged by the 2026-05-09
  // audit (AutoIssue #21). New fields land here when the template grows.
  metadata: HealthMetadata;
}

/**
 * Union of every per-service metadata field the health card template
 * renders. Each field is optional because each service supplies a
 * different subset. Adding a new metric: declare the field here, then
 * the template can compare/format it without TypeScript errors.
 *
 * Important — no index signature: a `[key: string]: unknown` catch-all
 * would widen every declared `number` field to `unknown` for the
 * Angular template-type-checker, breaking comparisons like
 * `meta.lag_hours > 48`. Adding a new field always requires a typed
 * declaration here.
 */
export interface HealthMetadata {
  lag_hours?: number;
  worker_count?: number;
  node_count?: number;
  plugin_count?: number;
  total_depth?: number;
  pipeline_depth?: number;
  usage_pct?: number;
  free_gb?: number;
  success_rate_7d?: number;
  failed_7d?: number;
  last_run_minutes_ago?: number;
  tokens_per_day_remaining?: number;
  embedding_model?: string;
  embedding_device?: string;
  active_model?: string;
  active_device?: string;
  active_dimension?: number;
  // Embedding hot-swap candidate fields (added 2026-05-09 alongside the
  // any-cleanup so the template-type-checker accepts comparisons).
  candidate_model?: string;
  candidate_status?: string;
  hot_swap_safe?: boolean;
  // Helper-PC fleet fields.
  online_count?: number;
  offline_count?: number;
  stale_count?: number;
  busy_count?: number;
  busiest_helper?: string;
  busiest_effective_load?: number;
  aggregate_ram_pressure?: number;
  // Backfill progress fields.
  backfill_status?: string;
  backfill_progress_pct?: number;
}

export interface DiskHealth {
  db_size_mb: number;
  embeddings_size_mb: number;
  items_count: number;
}

export interface GpuHealth {
  temp_c: number | null;
  vram_total_mb: number | null;
  vram_used_mb: number | null;
  utilization_pct: number | null;
  available: boolean;
}

export interface HealthSummary {
  system_status: 'healthy' | 'degraded' | 'critical';
  total_services: number;
  degraded_count: number;
  last_check_at: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class HealthService {
  private http = inject(HttpClient);
  private baseUrl = '/api/health';

  getHealthStatus(): Observable<ServiceHealth[]> {
    return this.http.get<ServiceHealth[] | { results: ServiceHealth[] }>(`${this.baseUrl}/`).pipe(
      map(res => Array.isArray(res) ? res : (res.results ?? [])),
      catchError(() => of([]))
    );
  }

  getSummary(): Observable<HealthSummary> {
    return this.http.get<HealthSummary>(`${this.baseUrl}/summary/`).pipe(
      catchError(() => of({ system_status: 'critical' as const, total_services: 0, degraded_count: 0, last_check_at: null }))
    );
  }

  checkAll(): Observable<unknown> {
    return this.http.post(`${this.baseUrl}/check-all/`, {});
  }

  checkService(serviceKey: string): Observable<ServiceHealth> {
    return this.http.post<ServiceHealth>(`${this.baseUrl}/${serviceKey}/check/`, {});
  }

  getDiskHealth(): Observable<DiskHealth> {
    return this.http.get<DiskHealth>('/api/health/disk/').pipe(
      catchError(() => of({ db_size_mb: 0, embeddings_size_mb: 0, items_count: 0 }))
    );
  }

  getGpuHealth(): Observable<GpuHealth> {
    return this.http.get<GpuHealth>('/api/health/gpu/').pipe(
      catchError(() => of({ temp_c: null, vram_total_mb: null, vram_used_mb: null, utilization_pct: null, available: false }))
    );
  }
}
