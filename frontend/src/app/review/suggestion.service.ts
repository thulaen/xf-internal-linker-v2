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
  score_link_freshness: number;
  score_phrase_relevance: number;
  score_learned_anchor_corroboration: number;
  host_sentence: number;
  anchor_start: number | null;
  anchor_end: number | null;
  applied_at: string | null;
  verified_at: string | null;
  stale_reason: string;
  superseded_by: string | null;
  superseded_at: string | null;
  phrase_match_diagnostics: PhraseMatchDiagnostics;
  learned_anchor_diagnostics: LearnedAnchorDiagnostics;
  link_freshness_diagnostics: LinkFreshnessDiagnostics;
  updated_at: string;
}

export interface PhraseMatchDiagnostics {
  score_phrase_relevance: number;
  phrase_match_state:
    | 'computed_exact_title'
    | 'computed_exact_distilled'
    | 'computed_partial_title'
    | 'computed_partial_distilled'
    | 'neutral_no_destination_phrases'
    | 'neutral_no_host_match'
    | 'neutral_partial_below_threshold'
    | 'fallback_current_extractor';
  selected_anchor_text: string | null;
  selected_anchor_start: number | null;
  selected_anchor_end: number | null;
  selected_match_type: 'exact' | 'partial' | 'none';
  selected_phrase_source: 'title' | 'distilled' | 'fallback' | 'none';
  selected_token_count: number;
  context_window_tokens: number;
  context_corroborating_hits: number;
  destination_phrase_count: number;
}

export interface LinkFreshnessDiagnostics {
  link_freshness_score: number;
  freshness_bucket: 'fresh' | 'neutral' | 'stale';
  freshness_data_state: 'computed' | 'neutral_missing_history' | 'neutral_thin_history' | 'neutral_invalid_history';
  total_peer_count: number;
  active_peer_count: number;
  recent_new_peer_count: number;
  previous_new_peer_count: number;
  recent_lost_peer_count: number;
  recent_share: number;
  growth_delta: number;
  cohort_freshness: number;
  recent_window_days: number;
  newest_peer_percent: number;
  min_peer_count: number;
}

export interface LearnedAnchorDiagnostics {
  score_learned_anchor_corroboration: number;
  learned_anchor_state:
    | 'exact_variant_match'
    | 'family_match'
    | 'host_contains_canonical_variant'
    | 'neutral_no_anchor_candidate'
    | 'neutral_no_learned_anchor_data'
    | 'neutral_below_min_sources'
    | 'neutral_no_family_match'
    | 'neutral_processing_error';
  candidate_anchor_text: string | null;
  candidate_anchor_normalized: string | null;
  matched_family_canonical: string | null;
  matched_variant_display: string | null;
  family_support_share: number;
  variant_support_share: number;
  supporting_source_count: number;
  usable_inbound_anchor_sources: number;
  learned_family_count: number;
  top_learned_families: Array<{
    canonical_anchor: string;
    support_share: number;
    supporting_source_count: number;
    alternate_variants: string[];
  }>;
  host_contains_canonical_variant: boolean;
  recommended_canonical_anchor: string | null;
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
