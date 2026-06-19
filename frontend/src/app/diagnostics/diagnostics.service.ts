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
  system_health?: {
    window_days: number;
    sample_count: number;
    neutral_fallback_count: number;
    neutral_fallback_rate: number | null;
    last_run_at: string | null;
    status_label: string;
    plain_english: string;
  } | null;
  governance?: {
    status: string;
    fr_id: string | null;
    spec_path: string | null;
    academic_source: string | null;
    source_kind: string | null;
    architecture_lane: string;
    neutral_value: number | null;
    min_data_threshold: string | null;
    diagnostic_surfaces: string[];
    benchmark_module: string | null;
    autotune_included: boolean;
    default_enabled: boolean;
    added_in_phase: string | null;
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

export type AccuracyLabStatus =
  | 'not_run'
  | 'running'
  | 'passed'
  | 'warning'
  | 'failed'
  | 'missing'
  | 'unknown';

export interface AccuracyLabCheck {
  id: string;
  name: string;
  status: AccuracyLabStatus;
  message: string;
  category?: string;
  summary?: string;
}

export interface AccuracyLabFinding {
  id: string;
  title: string;
  risk: 'critical' | 'high' | 'medium' | 'low' | 'info' | string;
  impact: string;
  evidence: string;
  affected: string;
  suggested_action: string;
}

export interface AccuracyLabSummary {
  generated_at: string | null;
  status: AccuracyLabStatus;
  message: string;
  summary: {
    total_findings: number;
    status: AccuracyLabStatus;
    risk_counts: Record<string, number>;
  };
  checks: AccuracyLabCheck[];
  sophisticated_checks?: AccuracyLabCheck[];
}

export interface AccuracyLabTools {
  generated_at: string | null;
  tools: {
    matlab?: {
      available: boolean;
      status: AccuracyLabStatus;
      version: string | null;
      java?: string | null;
      desktop?: boolean | null;
      path?: string | null;
      message?: string;
      cleanup_status?: string;
      runtime_seconds?: number | null;
      exit_code?: number | null;
      lingering_pids?: number[];
      thread_policy?: {
        min_cores: number;
        max_threads: number;
        thread_cap: number | null;
        core_count: number | null;
        status: string;
      };
    };
  };
}

export interface AccuracyLabFindingsResponse {
  generated_at: string | null;
  status: AccuracyLabStatus;
  findings: AccuracyLabFinding[];
}

export interface AccuracyLabRunResponse {
  status: AccuracyLabStatus;
  message: string;
  report: AccuracyLabSummary | null;
}

// Phase GT Step 10 — Runtime context snapshot captured with every error row.
export interface RuntimeContext {
  node_id: string;
  node_role: string;
  node_hostname: string;
  python_version: string;
  embedding_model: string;
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

export type DiagnosticsActionResponse = Record<string, unknown>;

/** Polish.B — daily NDCG@K readout over the reviewed-Suggestion stream.
 *  Mirrors the Python ``NdcgResult.to_dict`` shape. */
export interface NdcgEvalResult {
  available: boolean;
  /** Human-readable status line for the dashboard. */
  message: string;
  /** Empty when not yet available. */
  ndcg?: number;
  k?: number;
  sample_size?: number;
  sufficient_data?: boolean;
  sufficient_for_pairwise?: boolean;
  confidence_lower?: number;
  confidence_upper?: number;
  fitted_at?: string | null;
  /** Per-candidate-origin NDCG (only origins with ≥ basic floor sample). */
  breakdown_by_candidate_origin?: Record<string, number>;
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

  refreshServices(): Observable<DiagnosticsActionResponse> {
    return this.http.post<DiagnosticsActionResponse>(`${this.baseUrl}/services/refresh/`, {}).pipe(
      catchError(err => throwError(() => err))
    );
  }

  getConflicts(): Observable<SystemConflict[]> {
    return this.http.get<SystemConflict[]>(`${this.baseUrl}/conflicts/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  detectConflicts(): Observable<DiagnosticsActionResponse> {
    return this.http.post<DiagnosticsActionResponse>(`${this.baseUrl}/conflicts/detect/`, {}).pipe(
      catchError(err => throwError(() => err))
    );
  }

  resolveConflict(id: number): Observable<DiagnosticsActionResponse> {
    return this.http.patch<DiagnosticsActionResponse>(`${this.baseUrl}/conflicts/${id}/`, { resolved: true }).pipe(
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

  /** Polish.B — daily NDCG@K readout (paper-backed retriever quality). */
  getNdcgEval(): Observable<NdcgEvalResult> {
    return this.http.get<NdcgEvalResult>(`${this.baseUrl}/ndcg-eval/`).pipe(
      catchError(err => throwError(() => err)),
    );
  }

  getErrors(): Observable<ErrorLogEntry[]> {
    return this.http.get<ErrorLogEntry[]>(`${this.baseUrl}/errors/`).pipe(
      catchError(err => throwError(() => err))
    );
  }

  acknowledgeError(id: number): Observable<DiagnosticsActionResponse> {
    return this.http.post<DiagnosticsActionResponse>(`${this.baseUrl}/errors/${id}/acknowledge/`, {}).pipe(
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

  getAccuracyTools(): Observable<AccuracyLabTools> {
    return this.http
      .get<AccuracyLabTools>(`${this.baseUrl}/accuracy/tools/`)
      .pipe(catchError(err => throwError(() => err)));
  }

  getAccuracySummary(): Observable<AccuracyLabSummary> {
    return this.http
      .get<AccuracyLabSummary>(`${this.baseUrl}/accuracy/summary/`)
      .pipe(catchError(err => throwError(() => err)));
  }

  getAccuracyFindings(): Observable<AccuracyLabFindingsResponse> {
    return this.http
      .get<AccuracyLabFindingsResponse>(`${this.baseUrl}/accuracy/findings/`)
      .pipe(catchError(err => throwError(() => err)));
  }

  runAccuracyLab(): Observable<AccuracyLabRunResponse> {
    return this.http
      .post<AccuracyLabRunResponse>(`${this.baseUrl}/accuracy/run/`, {})
      .pipe(catchError(err => throwError(() => err)));
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
