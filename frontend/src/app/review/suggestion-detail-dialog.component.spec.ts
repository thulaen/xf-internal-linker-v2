import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
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
    score_phrase_relevance: 0.82,
    score_learned_anchor_corroboration: 0.91,
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
    updated_at: '2026-03-25T00:00:00Z',
  };

  it('renders March 2026 PageRank, Link Freshness, Phrase Relevance, and Learned Anchor Corroboration', async () => {
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
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SuggestionDetailDialogComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('March 2026 PageRank');
    expect(text).toContain('Link Freshness');
    expect(text).toContain('Phrase Relevance');
    expect(text).toContain('Learned Anchor Corroboration');
  });
});
