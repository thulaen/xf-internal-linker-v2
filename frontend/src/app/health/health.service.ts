import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ServiceHealth {
  service_key: string;
  service_name: string;
  service_description: string;
  status: 'healthy' | 'warning' | 'error' | 'down' | 'stale' | 'not_configured' | 'not_enabled';
  status_label: string;
  last_check_at: string;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_message: string;
  issue_description: string;
  suggested_fix: string;
  metadata: any;
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
    return this.http.get<ServiceHealth[]>(`${this.baseUrl}/`);
  }

  getSummary(): Observable<HealthSummary> {
    return this.http.get<HealthSummary>(`${this.baseUrl}/summary/`);
  }

  checkAll(): Observable<any> {
    return this.http.post(`${this.baseUrl}/check-all/`, {});
  }

  checkService(serviceKey: string): Observable<ServiceHealth> {
    return this.http.post<ServiceHealth>(`${this.baseUrl}/${serviceKey}/check/`, {});
  }
}
