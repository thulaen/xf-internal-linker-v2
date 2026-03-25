import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { SuggestionService, SuggestionDetail, REJECTION_REASONS } from './suggestion.service';
import { highlightText } from '../core/utils/highlight.utils';

export interface DialogData {
  suggestionId: string;
}

export type DialogResult =
  | { action: 'approved' | 'rejected' | 'applied'; suggestion: SuggestionDetail }
  | null;


@Component({
  selector: 'app-suggestion-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatChipsModule,
    MatDialogModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatTooltipModule,
  ],
  templateUrl: './suggestion-detail-dialog.component.html',
  styleUrls: ['./suggestion-detail-dialog.component.scss'],
})
export class SuggestionDetailDialogComponent implements OnInit {
  detail: SuggestionDetail | null = null;
  loading = true;
  error = '';
  saving = false;

  // Editable fields
  anchorEdited = '';
  reviewerNotes = '';
  rejectionReason = 'irrelevant';

  rejectionMode = false;
  readonly rejectionReasons = REJECTION_REASONS;

  readonly dialogRef = inject(MatDialogRef) as MatDialogRef<SuggestionDetailDialogComponent, DialogResult>;
  readonly data: DialogData = inject(MAT_DIALOG_DATA);
  private svc = inject(SuggestionService);

  ngOnInit(): void {
    this.svc.getDetail(this.data.suggestionId).subscribe({
      next: (d) => {
        this.detail = d;
        this.anchorEdited = d.anchor_edited || d.anchor_phrase;
        this.reviewerNotes = d.reviewer_notes ?? '';
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load suggestion details.';
        this.loading = false;
      },
    });
  }

  get effectiveAnchor(): string {
    return this.detail?.anchor_edited || this.detail?.anchor_phrase || '';
  }

  highlightSentence(sentence: string, anchor: string): string {
    return highlightText(sentence, anchor);
  }

  scorePercent(val: number): number {
    return Math.round(val * 100);
  }

  phraseSummary(): string {
    const diagnostics = this.detail?.phrase_match_diagnostics;
    if (!diagnostics) {
      return 'Neutral means the sentence did not provide useful phrase evidence.';
    }
    if (diagnostics.selected_match_type === 'partial') {
      return 'Partial means the sentence matched part of the destination phrase and nearby words supported it.';
    }
    if (diagnostics.selected_match_type === 'exact') {
      return 'Phrase relevance means the host sentence contains a destination phrase or a close local phrase match.';
    }
    return 'Neutral means the sentence did not provide useful phrase evidence.';
  }

  phraseStateLabel(): string {
    const state = this.detail?.phrase_match_diagnostics?.phrase_match_state ?? 'neutral_no_host_match';
    if (state === 'computed_exact_title') {
      return 'Exact title phrase';
    }
    if (state === 'computed_exact_distilled') {
      return 'Exact distilled-text phrase';
    }
    if (state === 'computed_partial_title') {
      return 'Partial title phrase';
    }
    if (state === 'computed_partial_distilled') {
      return 'Partial distilled-text phrase';
    }
    if (state === 'fallback_current_extractor') {
      return 'Fallback to current exact-title extractor';
    }
    if (state === 'neutral_no_destination_phrases') {
      return 'Neutral / no usable destination phrases';
    }
    if (state === 'neutral_partial_below_threshold') {
      return 'Neutral / partial phrase below threshold';
    }
    return 'Neutral / no useful phrase match';
  }

  linkFreshnessSummary(): string {
    const diagnostics = this.detail?.link_freshness_diagnostics;
    if (!diagnostics) {
      return 'Neutral means there is not enough link history yet.';
    }
    if (diagnostics.freshness_bucket === 'fresh') {
      return 'Fresh means this destination has newer or growing inbound links.';
    }
    if (diagnostics.freshness_bucket === 'stale') {
      return 'Stale means newer inbound-link growth has cooled off or links have recently disappeared.';
    }
    return 'Neutral means there is not enough link history yet.';
  }

  linkFreshnessStateLabel(): string {
    const state = this.detail?.link_freshness_diagnostics?.freshness_data_state ?? 'neutral_missing_history';
    if (state === 'computed') {
      return 'Computed from stored link history';
    }
    if (state === 'neutral_thin_history') {
      return 'Neutral / not enough link history';
    }
    if (state === 'neutral_invalid_history') {
      return 'Neutral / invalid link history';
    }
    return 'Neutral / not enough link history';
  }

  approve(): void {
    if (!this.detail || this.saving) return;
    this.saving = true;
    this.svc.approve(this.detail.suggestion_id, this.anchorEdited, this.reviewerNotes).subscribe({
      next: (s) => this.dialogRef.close({ action: 'approved', suggestion: s }),
      error: () => { this.saving = false; this.error = 'Approve failed.'; },
    });
  }

  startReject(): void {
    this.rejectionMode = true;
  }

  confirmReject(): void {
    if (!this.detail || this.saving) return;
    this.saving = true;
    this.svc.reject(this.detail.suggestion_id, this.rejectionReason, this.reviewerNotes).subscribe({
      next: (s) => this.dialogRef.close({ action: 'rejected', suggestion: s }),
      error: () => { this.saving = false; this.error = 'Reject failed.'; },
    });
  }

  apply(): void {
    if (!this.detail || this.saving) return;
    this.saving = true;
    this.svc.apply(this.detail.suggestion_id).subscribe({
      next: (s) => this.dialogRef.close({ action: 'applied', suggestion: s }),
      error: () => { this.saving = false; this.error = 'Apply failed.'; },
    });
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}
