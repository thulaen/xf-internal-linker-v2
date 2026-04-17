import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

/**
 * Phase MS — client for the Meta Algorithm Settings tab.
 *
 * Thin wrapper over `/api/meta-algorithms/` + `/toggle/`. Shape
 * matches `apps.suggestions.views.MetaAlgorithmSettingsView`.
 */

export type MetaStatus = 'active' | 'forward-declared' | 'disabled';

export interface MetaRow {
  id: string;
  meta_code: string;
  family: string;
  title: string;
  status: MetaStatus;
  enabled: boolean;
  enabled_key: string;
  weight_key: string | null;
  weight_value: string | null;
  spec_path: string | null;
  cpp_kernel: string | null;
  param_keys: string[];
}

export interface FamilySummary {
  family: string;
  total: number;
  active: number;
  disabled: number;
  forward: number;
}

export interface MetaAlgorithmsPayload {
  rows: MetaRow[];
  families: FamilySummary[];
  total: number;
}

export interface MetaFilter {
  family?: string;
  status?: MetaStatus | '';
  q?: string;
}

@Injectable({ providedIn: 'root' })
export class MetaAlgorithmsService {
  private http = inject(HttpClient);
  private readonly base = '/api/meta-algorithms/';

  list(filter: MetaFilter = {}): Observable<MetaAlgorithmsPayload> {
    let params = new HttpParams();
    if (filter.family) params = params.set('family', filter.family);
    if (filter.status) params = params.set('status', filter.status);
    if (filter.q) params = params.set('q', filter.q);
    return this.http.get<MetaAlgorithmsPayload>(this.base, { params });
  }

  toggle(id: string, enabled: boolean): Observable<{
    id: string;
    meta_code: string;
    enabled: boolean;
  }> {
    return this.http.post<{
      id: string;
      meta_code: string;
      enabled: boolean;
    }>(`${this.base}${encodeURIComponent(id)}/toggle/`, { enabled });
  }
}
