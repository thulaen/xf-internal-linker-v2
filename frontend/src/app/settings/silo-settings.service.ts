import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type SiloMode = 'disabled' | 'prefer_same_silo' | 'strict_same_silo';

export interface SiloSettings {
  mode: SiloMode;
  same_silo_boost: number;
  cross_silo_penalty: number;
}

export interface SiloGroup {
  id: number;
  name: string;
  slug: string;
  description: string;
  display_order: number;
  scope_count: number;
  created_at: string;
  updated_at: string;
}

export interface ScopeItem {
  id: number;
  scope_id: number;
  scope_type: string;
  title: string;
  parent: number | null;
  parent_title: string | null;
  silo_group: number | null;
  silo_group_name: string;
  is_enabled: boolean;
  content_count: number;
  display_order: number;
}

@Injectable({ providedIn: 'root' })
export class SiloSettingsService {
  private http = inject(HttpClient);

  getSettings(): Observable<SiloSettings> {
    return this.http.get<SiloSettings>('/api/settings/silos/');
  }

  updateSettings(payload: SiloSettings): Observable<SiloSettings> {
    return this.http.put<SiloSettings>('/api/settings/silos/', payload);
  }

  listSiloGroups(): Observable<SiloGroup[]> {
    return this.http.get<SiloGroup[]>('/api/silo-groups/');
  }

  createSiloGroup(payload: Partial<SiloGroup>): Observable<SiloGroup> {
    return this.http.post<SiloGroup>('/api/silo-groups/', payload);
  }

  updateSiloGroup(id: number, payload: Partial<SiloGroup>): Observable<SiloGroup> {
    return this.http.patch<SiloGroup>(`/api/silo-groups/${id}/`, payload);
  }

  deleteSiloGroup(id: number): Observable<void> {
    return this.http.delete<void>(`/api/silo-groups/${id}/`);
  }

  listScopes(): Observable<ScopeItem[]> {
    return this.http.get<ScopeItem[]>('/api/scopes/');
  }

  updateScopeSilo(id: number, siloGroupId: number | null): Observable<ScopeItem> {
    return this.http.patch<ScopeItem>(`/api/scopes/${id}/`, {
      silo_group: siloGroupId,
    });
  }
}
