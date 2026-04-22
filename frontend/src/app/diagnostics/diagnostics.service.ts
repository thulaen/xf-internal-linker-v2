import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface ServiceStatus {
  id: number;
  service_name: string;
  state: string;
  explanation: string;
  last_check: string;
  last_success: string | null;
  last_failure: string | null;
  next_action_step: string;
  metadata: ServiceMetadata;
}

export interface NativeModuleStatus {
  module: string;
  label: string;
  critical: boolean;
  compiled: boolean;
  importable: boolean;
  callable_present: boolean;
  state: string;
  runtime_path: 'cpp' | 'python';
  fallback_active: boolean;
  fallback_reason: string;
  origin: string;
  benchmark_status?: string;
  python_ms?: number | null;
  cpp_ms?: number | null;
  speedup_vs_python?: number | null;
  proof_available?: boolean;
  benchmark_error?: string;
}

export interface ServiceMetadata {
  runtime_path?: 'cpp' | 'python' | 'mixed' | string;
  fallback_active?: boolean;
  fallback_reason?: string;
  python_fallback_active?: boolean;
  compiled?: boolean;
  importable?: boolean;
  safe_to_use?: boolean;
  last_benchmark_ms?: number | null;
  speedup_vs_python?: number | null;
  benchmark_status?: string;
  module_statuses?: NativeModuleStatus[];
  owner_selected?: string;
  last_error_summary?: string;
  // Execution-specific metadata
  healthy_module_count?: number;
  degraded_module_count?: number;
  python_benchmark_ms?: number | null;
  cpp_fast_path_active?: boolean;
  worker_online?: boolean;
  scheduler_mode?: 'active' | 'shadow' | 'unknown' | string;
  // Lane-specific metadata
  broken_link_scan_owner?: string;
  graph_sync_owner?: string;
  import_owner?: string;
  pipeline_owner?: string;
  [key: string]: unknown;
}

export interface SystemConflict {
  id: number;
  conflict_type: string;
  title: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  location: string;
  why: string;
  next_step: string;
  resolved: boolean;
  created_at: string;
}

export interface FeatureReadiness {
  id: string;
  name: string;
  status: 'planned_only' | 'implementing' | 'implemented' | 'verified' | 'failed';
}

export interface ResourceUsage {
  cpu_percent: number | 'unavailable';
  ram_usage_mb: number | 'unavailable';
  disk_usage_percent: number | 'unavailable';
}

/**
 * Phase 1v — summary of the RejectedPair negative-memory table for the
 * Diagnostics page. See backend NegativeMemoryDiagnosticsView.
 */
export interface SuppressedPairsDiagnostics {
  active_suppression_window_days: number;
  active_suppressed_pairs: number;
  total_rejected_pairs: number;
  total_rejections_lifetime: number;
  most_recent_rejection_at: string | null;
}

/**
 * Tier 2 slice 4 — single row in the suppressed-pair drilldown. Returned by
 * NegativeMemoryListView. Host + destination titles are included so the
 * table doesn't need a second round-trip.
 */
export interface SuppressedPairListItem {
  id: number;
  host: { id: number; title: string; content_type: string };
  destination: { id: number; title: string; content_type: string };
  first_rejected_at: string;
  last_rejected_at: string;
  rejection_count: number;
  days_since_last: number;
  within_suppression_window: boolean;
}

export interface SuppressedPairListResponse {
  total: number;
  page: number;
  page_size: number;
  active_suppression_window_days: number;
  items: SuppressedPairListItem[];
}

export interface SuppressedPairClearResponse {
  detail: string;
  cleared_pair_id: number;
}

export interface DiagnosticsOverview {
  summary: {
    healthy: number;
    degraded: number;
    failed: number;
    not_configured: number;
    planned_only: number;
  };
  top_urgent_issues: SystemConflict[];
}

export interface WeightSignal {
  id: string;
  name: string;
  type: 'ranking' | 'value';
  description: string;
  weight: number | string;
  cpp_acceleration: {
    active: boolean;
    status_label: string;
    kernel: string | null;
  };
  storage: {
    table: string;
    row_count: number;
    size_bytes: number;
    size_human: string;
  };
  health: {
    status: 'healthy' | 'degraded';
    recent_errors: number;
  };
}

export interface WeightDiagnosticsResponse {
  signals: WeightSignal[];
  summary: {
    total_signals: number;
    cpp_accelerated_count: number;
    healthy_count: number;
    last_refreshed: string;
  };
}

// Phase GT Step 10 — Runtime context snapshot captured with every error row.
export interface RuntimeContext {
  node_id: string;
  node_role: string;
  node_hostname: string;
  python_version: string;
  embedding_model: string;
  gpu_available: boolean;
  cuda_version: string | null;
  gpu_name: string | null;
  spacy_model: string | null;
}

export interface ErrorLogEntry {
  id: number;
  job_type: string;
  step: string;
  error_message: string;
  raw_exception: string;
  why: string;
  acknowledged: boolean;
  created_at: string;

  // Phase GT fields — all optional so old snapshots still parse cleanly.
  source?: 'internal' | 'glitchtip';
  glitchtip_issue_id?: string | null;
  glitchtip_url?: string | null;
  fingerprint?: string | null;
  occurrence_count?: number;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  how_to_fix?: string;
  node_id?: string;
  node_role?: string;
  node_hostname?: string;
  runtime_context?: Partial<RuntimeContext>;

  // Derived (from ErrorLogSerializer).
  error_trend?: { date: string; count: number }[];
  related_error_ids?: number[];
}

export interface NodeSummary {
  node_id: string;
  node_role: string;
  node_hostname: string;
  last_seen: string | null;
  unacknowledged: number;
  total: number;
  worst_severity: 'critical' | 'high' | 'medium' | 'low';
}

export interface PipelineGateBlocker {
  check: string;
  state: string;
  explanation: string;
  next_step: string;
}

export interface PipelineGate {
  can_run: boolean;
  blockers: PipelineGateBlocker[];
}

@Injectable({ providedIn: 'root' })
export class DiagnosticsService {
  private http = inject(HttpClient);
  private baseUrl = '/api/system/status';

  getOverview(): Observable<DiagnosticsOverview> {
    return this.http.get<DiagnosticsOverview>(`${this.baseUrl}/overview/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getServices(): Observable<ServiceStatus[]> {
    return this.http.get<ServiceStatus[]>(`${this.baseUrl}/services/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  refreshServices(): Observable<any> {
    return this.http.post(`${this.baseUrl}/services/refresh/`, {}).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getConflicts(): Observable<SystemConflict[]> {
    return this.http.get<SystemConflict[]>(`${this.baseUrl}/conflicts/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  detectConflicts(): Observable<any> {
    return this.http.post(`${this.baseUrl}/conflicts/detect/`, {}).pipe(
      catchError(err => throwError(() => err))
    );
  }

  resolveConflict(id: number): Observable<any> {
    return this.http.patch(`${this.baseUrl}/conflicts/${id}/`, { resolved: true }).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getFeatures(): Observable<FeatureReadiness[]> {
    return this.http.get<FeatureReadiness[]>(`${this.baseUrl}/features/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getResources(): Observable<ResourceUsage> {
    return this.http.get<ResourceUsage>(`${this.baseUrl}/resources/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getErrors(): Observable<ErrorLogEntry[]> {
    return this.http.get<ErrorLogEntry[]>(`${this.baseUrl}/errors/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  acknowledgeError(id: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/errors/${id}/acknowledge/`, {}).pipe(
      catchError(err => throwError(() => err))
    );
  }

  // Phase GT Step 8 — re-dispatch the failing Celery task. Server-side
  // whitelist limits this to job_types that are safely re-runnable.
  rerunError(id: number): Observable<{ status: string; acknowledged?: boolean }> {
    return this.http.post<{ status: string; acknowledged?: boolean }>(
      `${this.baseUrl}/errors/${id}/rerun/`,
      {}
    ).pipe(catchError(err => throwError(() => err)));
  }

  // Phase GT Step 5 — operator intelligence endpoints.
  getRuntimeContext(): Observable<RuntimeContext> {
    return this.http.get<RuntimeContext>(`${this.baseUrl}/runtime-context/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getNodes(): Observable<NodeSummary[]> {
    return this.http.get<NodeSummary[]>(`${this.baseUrl}/nodes/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getPipelineGate(): Observable<PipelineGate> {
    return this.http.get<PipelineGate>(`${this.baseUrl}/pipeline-gate/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getWeightDiagnostics(): Observable<WeightDiagnosticsResponse> {
    return this.http.get<WeightDiagnosticsResponse>(`${this.baseUrl}/weights/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  /**
   * Phase 1v — counts for the Phase 1 negative-memory (RejectedPair) table.
   * Backed by NegativeMemoryDiagnosticsView.
   */
  getSuppressedPairs(): Observable<SuppressedPairsDiagnostics> {
    return this.http
      .get<SuppressedPairsDiagnostics>(`${this.baseUrl}/suppressed-pairs/`)
      .pipe(catchError(err => throwError(() => err)));
  }

  /**
   * Tier 2 slice 4 — paginated list of suppressed pairs for the Diagnostics
   * drilldown. Newest first.
   */
  getSuppressedPairsList(page = 1, pageSize = 25): Observable<SuppressedPairListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return this.http
      .get<SuppressedPairListResponse>(
        `${this.baseUrl}/suppressed-pairs/list/?${params.toString()}`,
      )
      .pipe(catchError(err => throwError(() => err)));
  }

  /**
   * Tier 2 slice 4 — manual clear. Deletes the RejectedPair row and writes
   * an AuditEntry so the action is visible on the Audit page.
   */
  clearSuppressedPair(pairId: number): Observable<SuppressedPairClearResponse> {
    return this.http
      .post<SuppressedPairClearResponse>(
        `${this.baseUrl}/suppressed-pairs/${pairId}/clear/`,
        {},
      )
      .pipe(catchError(err => throwError(() => err)));
  }

}
