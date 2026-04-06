import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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
  runtime_path?: 'cpp' | 'python' | 'csharp' | 'mixed' | string;
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

export interface ErrorLogEntry {
  id: number;
  job_type: string;
  step: string;
  error_message: string;
  raw_exception: string;
  why: string;
  acknowledged: boolean;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class DiagnosticsService {
  private http = inject(HttpClient);
  private baseUrl = '/api/system/status';

  getOverview(): Observable<DiagnosticsOverview> {
    return this.http.get<DiagnosticsOverview>(`${this.baseUrl}/overview/`);
  }

  getServices(): Observable<ServiceStatus[]> {
    return this.http.get<ServiceStatus[]>(`${this.baseUrl}/services/`);
  }

  refreshServices(): Observable<any> {
    return this.http.post(`${this.baseUrl}/services/refresh/`, {});
  }

  getConflicts(): Observable<SystemConflict[]> {
    return this.http.get<SystemConflict[]>(`${this.baseUrl}/conflicts/`);
  }

  detectConflicts(): Observable<any> {
    return this.http.post(`${this.baseUrl}/conflicts/detect/`, {});
  }

  resolveConflict(id: number): Observable<any> {
    return this.http.patch(`${this.baseUrl}/conflicts/${id}/`, { resolved: true });
  }

  getFeatures(): Observable<FeatureReadiness[]> {
    return this.http.get<FeatureReadiness[]>(`${this.baseUrl}/features/`);
  }

  getResources(): Observable<ResourceUsage> {
    return this.http.get<ResourceUsage>(`${this.baseUrl}/resources/`);
  }

  getErrors(): Observable<ErrorLogEntry[]> {
    return this.http.get<ErrorLogEntry[]>(`${this.baseUrl}/errors/`);
  }

  acknowledgeError(id: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/errors/${id}/acknowledge/`, {});
  }

  getWeightDiagnostics(): Observable<WeightDiagnosticsResponse> {
    return this.http.get<WeightDiagnosticsResponse>(`${this.baseUrl}/weights/`);
  }
}
