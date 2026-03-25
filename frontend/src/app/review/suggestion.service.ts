import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export type SuggestionStatus =
  | 'pending' | 'approved' | 'rejected'
  | 'applied' | 'verified' | 'stale' | 'superseded';

export type AnchorConfidence = 'strong' | 'weak' | 'none';

export interface Suggestion {
  suggestion_id: string;
  status: SuggestionStatus;
  score_final: number;
  destination: number;
  destination_title: string;
  destination_url: string;
  destination_content_type: string;
  destination_source_label: string;
  destination_silo_group: number | null;
  destination_silo_group_name: string;
  host: number;
  host_title: string;
  host_sentence_text: string;
  host_content_type: string;
  host_source_label: string;
  host_silo_group: number | null;
  host_silo_group_name: string;
  same_silo: boolean;
  anchor_phrase: string;
  anchor_edited: string;
  anchor_confidence: AnchorConfidence;
  repeated_anchor: boolean;
  rejection_reason: string;
  reviewer_notes?: string;
  reviewed_at: string | null;
  is_applied: boolean;
  created_at: string;
}

export interface SuggestionDetail extends Suggestion {
  pipeline_run: string;
  score_semantic: number;
  score_keyword: number;
  score_node_affinity: number;
  score_quality: number;
  score_march_2026_pagerank: number;
  score_velocity: number;
  host_sentence: number;
  anchor_start: number | null;
  anchor_end: number | null;
  applied_at: string | null;
  verified_at: string | null;
  stale_reason: string;
  superseded_by: string | null;
  superseded_at: string | null;
  updated_at: string;
}

export interface PaginatedResult<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface SuggestionFilters {
  status?: string;
  search?: string;
  ordering?: string;
  page?: number;
  same_silo?: boolean;
}

export const REJECTION_REASONS = [
  { value: 'irrelevant',     label: 'Irrelevant / off-topic' },
  { value: 'low_quality',   label: 'Low quality match' },
  { value: 'already_linked', label: 'Already linked' },
  { value: 'bad_anchor',    label: 'Bad anchor text' },
  { value: 'wrong_context', label: 'Wrong context' },
  { value: 'duplicate',     label: 'Duplicate suggestion' },
  { value: 'other',         label: 'Other' },
] as const;

export interface PipelineRun {
  run_id: string;
  run_state: string;
  rerun_mode: string;
  suggestions_created: number;
  destinations_processed: number;
  duration_display: string | null;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class SuggestionService {
  private http = inject(HttpClient);
  private base = '/api/suggestions/';
  private runsBase = '/api/pipeline-runs/';

  list(filters: SuggestionFilters = {}): Observable<PaginatedResult<Suggestion>> {
    let params = new HttpParams();
    if (filters.status && filters.status !== 'all') {
      params = params.set('status', filters.status);
    }
    if (filters.search?.trim()) {
      params = params.set('search', filters.search.trim());
    }
    if (filters.ordering) {
      params = params.set('ordering', filters.ordering);
    }
    if (filters.page && filters.page > 1) {
      params = params.set('page', String(filters.page));
    }
    if (filters.same_silo) {
      params = params.set('same_silo', 'true');
    }
    return this.http.get<PaginatedResult<Suggestion>>(this.base, { params });
  }

  getDetail(id: string): Observable<SuggestionDetail> {
    return this.http.get<SuggestionDetail>(`${this.base}${id}/`);
  }

  approve(id: string, anchorEdited?: string, notes?: string): Observable<SuggestionDetail> {
    const body: Record<string, string> = {};
    if (anchorEdited !== undefined) body['anchor_edited'] = anchorEdited;
    if (notes !== undefined) body['reviewer_notes'] = notes;
    return this.http.post<SuggestionDetail>(`${this.base}${id}/approve/`, body);
  }

  reject(id: string, reason: string, notes?: string): Observable<SuggestionDetail> {
    return this.http.post<SuggestionDetail>(`${this.base}${id}/reject/`, {
      rejection_reason: reason,
      reviewer_notes: notes ?? '',
    });
  }

  apply(id: string): Observable<SuggestionDetail> {
    return this.http.post<SuggestionDetail>(`${this.base}${id}/apply/`, {});
  }

  batchAction(
    action: 'approve' | 'reject' | 'skip',
    ids: string[],
    rejectionReason?: string
  ): Observable<{ updated: number }> {
    const body: Record<string, unknown> = { action, ids };
    if (rejectionReason) body['rejection_reason'] = rejectionReason;
    return this.http.post<{ updated: number }>(`${this.base}batch_action/`, body);
  }

  startPipeline(
    rerunMode = 'skip_pending',
    hostScope: Record<string, unknown> = {},
    destinationScope: Record<string, unknown> = {}
  ): Observable<PipelineRun> {
    return this.http.post<PipelineRun>(`${this.runsBase}start/`, {
      rerun_mode: rerunMode,
      host_scope: hostScope,
      destination_scope: destinationScope,
    });
  }

}
