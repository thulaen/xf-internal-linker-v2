import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import {
  SuggestionService,
  Suggestion,
  SuggestionFilters,
  REJECTION_REASONS,
} from './suggestion.service';
import { highlightText } from '../core/utils/highlight.utils';
import {
  SuggestionDetailDialogComponent,
  DialogData,
  DialogResult,
} from './suggestion-detail-dialog.component';

interface StatusTab {
  value: string;
  label: string;
  count?: number;
}


@Component({
  selector: 'app-review',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatChipsModule,
    MatDialogModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatMenuModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './review.component.html',
  styleUrls: ['./review.component.scss'],
})
export class ReviewComponent implements OnInit {
  private svc = inject(SuggestionService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private sanitizer = inject(DomSanitizer);

  // ── Data ─────────────────────────────────────────────────────────
  suggestions: Suggestion[] = [];
  totalCount = 0;
  loading = false;
  startingPipeline = false;

  // ── Filters ──────────────────────────────────────────────────────
  statusFilter = 'pending';
  searchQuery = '';
  sortBy = '-score_final';
  page = 1;
  pageSize = 25;

  statusTabs: StatusTab[] = [
    { value: 'pending',  label: 'Pending' },
    { value: 'approved', label: 'Approved' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'applied',  label: 'Applied' },
    { value: 'all',      label: 'All' },
  ];

  sortOptions = [
    { value: '-score_final', label: 'Score (high → low)' },
    { value: 'score_final',  label: 'Score (low → high)' },
    { value: '-created_at',  label: 'Newest first' },
    { value: 'created_at',   label: 'Oldest first' },
  ];

  rejectionReasons = REJECTION_REASONS;

  // ── Selection ────────────────────────────────────────────────────
  selectedIds = new Set<string>();

  get allSelected(): boolean {
    return this.suggestions.length > 0 &&
      this.suggestions.every(s => this.selectedIds.has(s.suggestion_id));
  }

  get someSelected(): boolean {
    return this.selectedIds.size > 0 && !this.allSelected;
  }

  // ── Lifecycle ────────────────────────────────────────────────────

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    const filters: SuggestionFilters = {
      status: this.statusFilter,
      search: this.searchQuery,
      ordering: this.sortBy,
      page: this.page,
    };
    this.svc.list(filters).subscribe({
      next: (res) => {
        this.suggestions = res.results;
        this.totalCount = res.count;
        this.loading = false;
        this.selectedIds.clear();
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load suggestions', 'Dismiss', { duration: 4000 });
      },
    });
  }

  // ── Filter handlers ──────────────────────────────────────────────

  setStatus(value: string): void {
    this.statusFilter = value;
    this.page = 1;
    this.load();
  }

  onSearch(): void {
    this.page = 1;
    this.load();
  }

  onSortChange(): void {
    this.page = 1;
    this.load();
  }

  onPageChange(evt: PageEvent): void {
    this.page = evt.pageIndex + 1;
    this.load();
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.page = 1;
    this.load();
  }

  // ── Selection ────────────────────────────────────────────────────

  toggleSelect(id: string): void {
    if (this.selectedIds.has(id)) {
      this.selectedIds.delete(id);
    } else {
      this.selectedIds.add(id);
    }
  }

  toggleSelectAll(): void {
    if (this.allSelected) {
      this.selectedIds.clear();
    } else {
      this.suggestions.forEach(s => this.selectedIds.add(s.suggestion_id));
    }
  }

  isSelected(id: string): boolean {
    return this.selectedIds.has(id);
  }

  // ── Quick actions (inline) ────────────────────────────────────────

  quickApprove(s: Suggestion, event: Event): void {
    event.stopPropagation();
    this.svc.approve(s.suggestion_id).subscribe({
      next: (updated) => {
        this.replaceSuggestion(updated);
        this.snack.open('Approved', undefined, { duration: 2000 });
      },
      error: () => this.snack.open('Failed to approve', 'Dismiss', { duration: 4000 }),
    });
  }

  quickReject(s: Suggestion, reason: string, event: Event): void {
    event.stopPropagation();
    this.svc.reject(s.suggestion_id, reason).subscribe({
      next: (updated) => {
        this.replaceSuggestion(updated);
        this.snack.open('Rejected', undefined, { duration: 2000 });
      },
      error: () => this.snack.open('Failed to reject', 'Dismiss', { duration: 4000 }),
    });
  }

  // ── Batch actions ────────────────────────────────────────────────

  batchApprove(): void {
    const ids = [...this.selectedIds];
    this.svc.batchAction('approve', ids).subscribe({
      next: ({ updated }) => {
        this.snack.open(`Approved ${updated} suggestions`, undefined, { duration: 3000 });
        this.load();
      },
      error: () => this.snack.open('Batch approve failed', 'Dismiss', { duration: 4000 }),
    });
  }

  batchReject(reason: string): void {
    const ids = [...this.selectedIds];
    this.svc.batchAction('reject', ids, reason).subscribe({
      next: ({ updated }) => {
        this.snack.open(`Rejected ${updated} suggestions`, undefined, { duration: 3000 });
        this.load();
      },
      error: () => this.snack.open('Batch reject failed', 'Dismiss', { duration: 4000 }),
    });
  }

  // ── Detail dialog ─────────────────────────────────────────────────

  openDetail(s: Suggestion): void {
    const ref = this.dialog.open<
      SuggestionDetailDialogComponent,
      DialogData,
      DialogResult
    >(SuggestionDetailDialogComponent, {
      data: { suggestionId: s.suggestion_id },
      maxWidth: '720px',
      width: '95vw',
    });

    ref.afterClosed().subscribe((result) => {
      if (result) {
        this.replaceSuggestion(result.suggestion);
        const msgs: Record<string, string> = {
          approved: 'Suggestion approved',
          rejected: 'Suggestion rejected',
          applied:  'Marked as applied',
        };
        this.snack.open(msgs[result.action] ?? 'Saved', undefined, { duration: 2500 });
      }
    });
  }

  // ── Pipeline trigger ─────────────────────────────────────────────

  runPipeline(): void {
    this.startingPipeline = true;
    this.svc.startPipeline().subscribe({
      next: (run) => {
        this.startingPipeline = false;
        this.snack.open(
          `Pipeline started (run ${run.run_id.slice(0, 8)})`,
          'Dismiss',
          { duration: 5000 }
        );
      },
      error: () => {
        this.startingPipeline = false;
        this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
      },
    });
  }

  // ── Template helpers ─────────────────────────────────────────────

  highlightAnchor(sentence: string, suggestion: Suggestion): SafeHtml {
    const anchor = suggestion.anchor_edited || suggestion.anchor_phrase;
    return this.sanitizer.bypassSecurityTrustHtml(highlightText(sentence, anchor));
  }

  scoreColor(score: number): string {
    if (score >= 0.75) return 'high';
    if (score >= 0.5)  return 'medium';
    return 'low';
  }

  trackById(_: number, s: Suggestion): string {
    return s.suggestion_id;
  }

  private replaceSuggestion(updated: { suggestion_id: string; status: string } & Partial<Suggestion>): void {
    const idx = this.suggestions.findIndex(s => s.suggestion_id === updated.suggestion_id);
    if (idx !== -1) {
      this.suggestions[idx] = { ...this.suggestions[idx], ...updated };
    }
  }
}
