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
  metadata: any;
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

  getErrors(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/errors/`);
  }

  acknowledgeError(id: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/errors/${id}/acknowledge/`, {});
  }
}
