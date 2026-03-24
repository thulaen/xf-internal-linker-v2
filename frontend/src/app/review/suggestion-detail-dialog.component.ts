import { Component, Inject, OnInit } from '@angular/core';
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
import { SuggestionService, SuggestionDetail } from './suggestion.service';

export interface DialogData {
  suggestionId: string;
}

export type DialogResult =
  | { action: 'approved' | 'rejected' | 'applied'; suggestion: SuggestionDetail }
  | null;

const REJECTION_REASONS = [
  { value: 'irrelevant',    label: 'Irrelevant / off-topic' },
  { value: 'low_quality',  label: 'Low quality match' },
  { value: 'already_linked', label: 'Already linked' },
  { value: 'bad_anchor',   label: 'Bad anchor text' },
  { value: 'wrong_context', label: 'Wrong context' },
  { value: 'duplicate',    label: 'Duplicate suggestion' },
  { value: 'other',        label: 'Other' },
];

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
  rejectionReasons = REJECTION_REASONS;

  constructor(
    public dialogRef: MatDialogRef<SuggestionDetailDialogComponent, DialogResult>,
    @Inject(MAT_DIALOG_DATA) public data: DialogData,
    private svc: SuggestionService,
  ) {}

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
    // HTML-escape raw text first so forum content with tags (e.g. <b>, <img>)
    // is displayed as literal characters, not rendered markup.
    const safeSentence = this.escapeHtml(sentence ?? '');
    if (!anchor) return safeSentence;
    const safeAnchor = this.escapeHtml(anchor);
    const reEsc = safeAnchor.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return safeSentence.replace(new RegExp(`(${reEsc})`, 'gi'), '<mark>$1</mark>');
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
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
