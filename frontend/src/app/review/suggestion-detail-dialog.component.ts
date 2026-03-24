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
