import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

import { SuggestionDetailDialogComponent } from './suggestion-detail-dialog.component';
import { SuggestionDetail, SuggestionService } from './suggestion.service';

describe('SuggestionDetailDialogComponent', () => {
  const detail: SuggestionDetail = {
    suggestion_id: 'suggestion-1',
    pipeline_run: 'run-1',
    status: 'pending',
    score_final: 0.8,
    destination: 1,
    destination_title: 'Destination',
    destination_url: 'https://example.com/destination',
    destination_content_type: 'thread',
    destination_source_label: 'XenForo',
    destination_silo_group: null,
    destination_silo_group_name: '',
    host: 2,
    host_title: 'Host',
    host_sentence_text: 'Useful sentence about Destination',
    host_content_type: 'thread',
    host_source_label: 'XenForo',
    host_silo_group: null,
    host_silo_group_name: '',
    same_silo: false,
    anchor_phrase: 'Destination',
    anchor_edited: '',
    anchor_confidence: 'strong',
    repeated_anchor: false,
    rejection_reason: '',
    reviewer_notes: '',
    reviewed_at: null,
    is_applied: false,
    created_at: '2026-03-25T00:00:00Z',
    score_semantic: 0.8,
    score_keyword: 0.4,
    score_node_affinity: 0.3,
    score_quality: 0.2,
    score_march_2026_pagerank: 0.18,
    score_velocity: 0.1,
    score_link_freshness: 0.5,
    score_ga4_gsc: 0.5,
    score_phrase_relevance: 0.82,
    score_learned_anchor_corroboration: 0.91,
    score_rare_term_propagation: 0.88,
    score_field_aware_relevance: 0.86,
    score_click_distance: 0.7,
    score_slate_diversity: 0.64,
    host_sentence: 10,
    anchor_start: 22,
    anchor_end: 33,
    applied_at: null,
    verified_at: null,
    stale_reason: '',
    superseded_by: null,
    superseded_at: null,
    phrase_match_diagnostics: {
      score_phrase_relevance: 0.82,
      phrase_match_state: 'computed_exact_title',
      selected_anchor_text: 'Destination',
      selected_anchor_start: 22,
      selected_anchor_end: 33,
      selected_match_type: 'exact',
      selected_phrase_source: 'title',
      selected_token_count: 1,
      context_window_tokens: 8,
      context_corroborating_hits: 1,
      destination_phrase_count: 5,
    },
    learned_anchor_diagnostics: {
      score_learned_anchor_corroboration: 0.91,
      learned_anchor_state: 'exact_variant_match',
      candidate_anchor_text: 'Destination',
      candidate_anchor_normalized: 'destination',
      matched_family_canonical: 'Destination',
      matched_variant_display: 'Destination',
      family_support_share: 1,
      variant_support_share: 1,
      supporting_source_count: 3,
      usable_inbound_anchor_sources: 3,
      learned_family_count: 1,
      top_learned_families: [
        {
          canonical_anchor: 'Destination',
          support_share: 1,
          supporting_source_count: 3,
          alternate_variants: [],
        },
      ],
      host_contains_canonical_variant: false,
      recommended_canonical_anchor: 'Destination',
    },
    rare_term_diagnostics: {
      score_rare_term_propagation: 0.88,
      rare_term_state: 'computed_match',
      original_destination_terms: ['guide', 'internal', 'links'],
      propagated_term_candidates: [
        {
          term: 'xenforo',
          document_frequency: 2,
          supporting_related_pages: 2,
          supporting_relationship_weights: [1, 0.75],
          average_relationship_weight: 0.875,
          term_evidence: 0.76,
        },
      ],
      matched_propagated_terms: [
        {
          term: 'xenforo',
          document_frequency: 2,
          supporting_related_pages: 2,
          supporting_relationship_weights: [1, 0.75],
          average_relationship_weight: 0.875,
          term_evidence: 0.76,
        },
      ],
      top_propagated_terms: [
        {
          term: 'xenforo',
          document_frequency: 2,
          supporting_related_pages: 2,
          supporting_relationship_weights: [1, 0.75],
          average_relationship_weight: 0.875,
          term_evidence: 0.76,
        },
      ],
      eligible_related_page_count: 2,
      related_page_summary: [
        {
          content_id: 3,
          relationship_tier: 'same_scope',
          shared_original_token_count: 2,
        },
      ],
      max_document_frequency: 3,
      minimum_supporting_related_pages: 2,
    },
    field_aware_diagnostics: {
      score_field_aware_relevance: 0.86,
      field_aware_state: 'computed_match',
      field_weights: {
        title: 0.4,
        body: 0.3,
        scope: 0.15,
        learned_anchor: 0.15,
      },
      field_lengths: {
        title: 2,
        body: 4,
        scope: 1,
        learned_anchor: 1,
      },
      matched_field_count: 3,
      field_scores: {
        title: { score: 0.8, matched_terms: [{ token: 'destination', field_tf: 1, host_tf: 1, field_presence_count: 2, idf: 0.5, token_score: 0.6 }] },
        body: { score: 0.7, matched_terms: [{ token: 'guide', field_tf: 1, host_tf: 1, field_presence_count: 1, idf: 0.9, token_score: 0.8 }] },
        scope: { score: 0.6, matched_terms: [{ token: 'forum', field_tf: 1, host_tf: 1, field_presence_count: 1, idf: 0.9, token_score: 0.7 }] },
        learned_anchor: { score: 0.0, matched_terms: [] },
      },
    },
    link_freshness_diagnostics: {
      link_freshness_score: 0.5,
      freshness_bucket: 'neutral',
      freshness_data_state: 'neutral_thin_history',
      total_peer_count: 1,
      active_peer_count: 1,
      recent_new_peer_count: 1,
      previous_new_peer_count: 0,
      recent_lost_peer_count: 0,
      recent_share: 1,
      growth_delta: 1,
      cohort_freshness: 0,
      recent_window_days: 30,
      newest_peer_percent: 0.25,
      min_peer_count: 3,
    },
    click_distance_diagnostics: {
      click_distance_score: 0.7,
      click_distance_state: 'computed',
      source_url: 'https://example.com/host',
      click_distance: 2,
      url_depth: 1,
      combined_depth: 1.5,
      k_cd: 4,
      b_cd: 0.75,
      b_ud: 0.25
    },
    score_cluster_suppression: 0,
    cluster_diagnostics: {
      score_cluster_suppression: 0,
      clustering_state: 'neutral_no_cluster',
      cluster_id: null,
      is_canonical: true,
      member_count: 1,
      canonical_title: null,
      similarity_threshold: 0.04,
      suppression_penalty: 20
    },
    score_explore_exploit: 0.05,
    explore_exploit_diagnostics: {
      score_explore_exploit: 0.05,
      rerank_state: 'neutral_no_historical_data',
      exploit_score: 0,
      explore_score: 0.05,
      successes: 0,
      total_attempts: 0,
      global_attempts: 100,
      ranking_weight: 0.08,
      exploration_rate: 1.41
    },
    slate_diversity_diagnostics: {
      mmr_applied: true,
      lambda: 0.65,
      score_window: 0.3,
      slot: 1,
      relevance_normalized: 0.8,
      max_similarity_to_selected: 0.23,
      mmr_score: 0.45,
      swapped_from_rank: 1,
      similarity_cap: 0.9,
      flagged_redundant: false,
      window_source: 'score_window',
      runtime_path: 'python_fallback',
      runtime_reason: 'Python fallback is active because the native C++ MMR kernel is not compiled or could not be loaded.',
      algorithm_version: 'fr015-v1',
    },
    telemetry_instrumentation: {
      status: 'instrumented',
      event_schema: 'fr016_v1',
      attributes: {
        'data-xfil-schema': 'fr016_v1',
        'data-xfil-suggestion-id': 'suggestion-1',
      },
      anchor_hash: 'abc123def456',
      anchor_length: 11,
      instrumented_markup: '<a href="https://example.com/destination" data-xfil-schema="fr016_v1">Destination</a>',
    },
    updated_at: '2026-03-25T00:00:00Z',
  };

  it('renders March 2026 PageRank, Link Freshness, Phrase Relevance, Learned Anchor Corroboration, Rare-Term Propagation, and Field-Aware Relevance', async () => {
    await TestBed.configureTestingModule({
      imports: [SuggestionDetailDialogComponent, NoopAnimationsModule],
      providers: [
        {
          provide: SuggestionService,
          useValue: {
            getDetail: () => of(detail),
            approve: () => of(detail),
            reject: () => of(detail),
            apply: () => of(detail),
          },
        },
        { provide: MAT_DIALOG_DATA, useValue: { suggestionId: detail.suggestion_id } },
        { provide: MatDialogRef, useValue: { close: jasmine.createSpy('close') } },
        { provide: MatSnackBar, useValue: { open: jasmine.createSpy('open') } },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SuggestionDetailDialogComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('March 2026 PageRank');
    expect(text).toContain('Link Freshness');
    expect(text).toContain('Phrase Relevance');
    expect(text).toContain('Learned Anchor Corroboration');
    expect(text).toContain('Rare-Term Propagation');
    expect(text).toContain('Field-Aware Relevance');
    expect(text).toContain('Slate Diversity');
    expect(text).toContain('Matched borrowed terms: xenforo (2 pages)');
    expect(text).toContain('Top title terms: destination');
    expect(text).toContain('Promoted for variety');
    expect(text).toContain('Copy Instrumented Markup');
  });
});
