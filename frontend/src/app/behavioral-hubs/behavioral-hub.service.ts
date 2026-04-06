import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SessionCoOccurrencePair {
  id: number;
  source_content_item_id: number;
  dest_content_item_id: number;
  source_title: string;
  dest_title: string;
  co_session_count: number;
  source_session_count: number;
  dest_session_count: number;
  jaccard_similarity: number;
  lift: number;
  data_window_start: string;
  data_window_end: string;
  last_computed_at: string;
}

export interface SessionCoOccurrenceRun {
  run_id: string;
  status: 'running' | 'completed' | 'failed';
  data_window_start: string;
  data_window_end: string;
  sessions_processed: number;
  pairs_written: number;
  ga4_rows_fetched: number;
  started_at: string;
  completed_at: string | null;
  error_message: string;
}

export interface BehavioralHubMembership {
  id: number;
  content_item_id: number;
  content_item_title: string;
  content_item_url: string;
  membership_source: 'auto_detected' | 'manual_add' | 'manual_remove_override';
  co_occurrence_strength: number;
  created_at: string;
}

export interface BehavioralHub {
  hub_id: string;
  name: string;
  detection_method: 'threshold_connected_components' | 'manual';
  min_jaccard_used: number;
  member_count: number;
  auto_link_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface BehavioralHubDetail extends BehavioralHub {
  members: BehavioralHubMembership[];
}

export interface CoOccurrenceSettings {
  cooccurrence_enabled: boolean;
  data_window_days: number;
  min_co_session_count: number;
  min_jaccard: number;
  hub_min_jaccard: number;
  hub_min_members: number;
  hub_detection_enabled: boolean;
  schedule_weekly: boolean;
  last_run_at: string | null;
  last_run_pairs_written: number;
  last_run_hubs_detected: number;
}

export interface PaginatedResult<T> {
  count: number;
  results: T[];
}

@Injectable({ providedIn: 'root' })
export class BehavioralHubService {
  private http = inject(HttpClient);
  private base = '/api';

  getHubs(page = 1, pageSize = 25): Observable<PaginatedResult<BehavioralHub>> {
    const params = new HttpParams()
      .set('page', String(page))
      .set('page_size', String(pageSize));
    return this.http.get<PaginatedResult<BehavioralHub>>(`${this.base}/behavioral-hubs/`, { params });
  }

  getHub(hubId: string): Observable<BehavioralHubDetail> {
    return this.http.get<BehavioralHubDetail>(`${this.base}/behavioral-hubs/${hubId}/`);
  }

  patchHub(hubId: string, payload: Partial<Pick<BehavioralHub, 'name' | 'auto_link_enabled'>>): Observable<BehavioralHub> {
    return this.http.patch<BehavioralHub>(`${this.base}/behavioral-hubs/${hubId}/`, payload);
  }

  addMember(hubId: string, contentItemId: number): Observable<void> {
    return this.http.post<void>(`${this.base}/behavioral-hubs/${hubId}/members/`, { content_item_id: contentItemId });
  }

  removeMember(hubId: string, contentItemId: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/behavioral-hubs/${hubId}/members/${contentItemId}/`);
  }

  triggerDetection(): Observable<{ task_id: string; status: string }> {
    return this.http.post<{ task_id: string; status: string }>(`${this.base}/behavioral-hubs/detect/`, {});
  }

  getPairs(sourceId?: number, minJaccard?: number): Observable<PaginatedResult<SessionCoOccurrencePair>> {
    let params = new HttpParams();
    if (minJaccard !== undefined) params = params.set('min_jaccard', String(minJaccard));
    if (sourceId) {
      return this.http.get<PaginatedResult<SessionCoOccurrencePair>>(
        `${this.base}/cooccurrence/pairs/${sourceId}/`,
        { params }
      );
    }
    return this.http.get<PaginatedResult<SessionCoOccurrencePair>>(
      `${this.base}/cooccurrence/pairs/`,
      { params }
    );
  }

  getRuns(): Observable<SessionCoOccurrenceRun[]> {
    return this.http.get<SessionCoOccurrenceRun[]>(`${this.base}/cooccurrence/runs/`);
  }

  triggerCompute(): Observable<{ task_id: string; status: string }> {
    return this.http.post<{ task_id: string; status: string }>(`${this.base}/cooccurrence/compute/`, {});
  }

  getSettings(): Observable<CoOccurrenceSettings> {
    return this.http.get<CoOccurrenceSettings>(`${this.base}/settings/cooccurrence/`);
  }

  putSettings(payload: Partial<CoOccurrenceSettings>): Observable<CoOccurrenceSettings> {
    return this.http.put<CoOccurrenceSettings>(`${this.base}/settings/cooccurrence/`, payload);
  }
}
