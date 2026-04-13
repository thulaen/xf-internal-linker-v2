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
  metadata: any;
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
