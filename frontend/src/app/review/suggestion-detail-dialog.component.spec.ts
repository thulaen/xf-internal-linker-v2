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
    host_sentence: 10,
    anchor_start: 22,
    anchor_end: 33,
    applied_at: null,
    verified_at: null,
    stale_reason: '',
    superseded_by: null,
    superseded_at: null,
    updated_at: '2026-03-25T00:00:00Z',
  };

  it('renders March 2026 PageRank', async () => {
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
  });
});
