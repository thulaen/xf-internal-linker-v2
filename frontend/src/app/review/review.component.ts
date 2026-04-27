import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
import {
  SuggestionService,
  Suggestion,
  SuggestionFilters,
  REJECTION_REASONS,
} from './suggestion.service';
import { HighlightPipe } from '../core/pipes/highlight.pipe';
import { RunPipelineDialogComponent, RunPipelineDialogResult } from '../core/run-pipeline-dialog.component';
import {
  SuggestionDetailDialogComponent,
  DialogData,
  DialogResult,
} from './suggestion-detail-dialog.component';
import { ConfidenceBadgeComponent } from '../shared/confidence-badge/confidence-badge.component';
// Phase SR — readiness gate. The page holds rendering until the
// readiness service reports every prerequisite ready, unless the user
// has manually overridden via the "Show me anyway" button.
import { PreparingSuggestionsComponent } from './preparing-suggestions/preparing-suggestions.component';
import { SuggestionReadinessService } from '../core/services/suggestion-readiness.service';

interface StatusTab {
  value: string;
  label: string;
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
    HighlightPipe,
    ConfidenceBadgeComponent,
    // Phase SR — panel shown when the readiness gate reports a block.
    PreparingSuggestionsComponent,
  ],
  templateUrl: './review.component.html',
  styleUrls: ['./review.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReviewComponent implements OnInit {
  private svc = inject(SuggestionService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);
  // Phase SR — public so the template can read `readiness.ready()` /
  // `readiness.blocking()` directly. The service exposes signals so
  // the computed `isReadyForSuggestions` below stays reactive.
  readiness = inject(SuggestionReadinessService);

  /** Phase SR — operator-pressed override. When true, the gate is
   *  treated as "ready" for the remainder of this browser session
   *  so power users can unblock themselves without waiting for the
   *  prerequisites to flip. Not persisted — expires on reload. */
  readonly gateOverride = signal(false);

  // ── Data ─────────────────────────────────────────────────────────
  readonly suggestions = signal<Suggestion[]>([]);
  readonly totalCount = signal(0);
  readonly loading = signal(false);
  readonly startingPipeline = signal(false);

  // ── Filters ──────────────────────────────────────────────────────
  // ngModel two-way bindings need lvalues — these stay plain. (ngModelChange)
  // handlers fire on the host, so OnPush re-evaluates downstream bindings
  // (`@if (searchQuery)`, `[class.active]="statusFilter === ..."`) per keystroke.
  statusFilter = 'pending';
  searchQuery = '';
  sortBy = '-score_final';
  sameSiloOnly = false;

  // Pagination state — read by mat-paginator bindings.
  readonly page = signal(1);
  readonly pageSize = signal(25);

  readonly statusTabs: readonly StatusTab[] = [
    { value: 'pending',  label: 'Pending' },
    { value: 'approved', label: 'Approved' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'applied',  label: 'Applied' },
    { value: 'all',      label: 'All' },
  ];

  readonly sortOptions = [
    { value: '-score_final', label: 'Score (high → low)' },
    { value: 'score_final',  label: 'Score (low → high)' },
    { value: '-created_at',  label: 'Newest first' },
    { value: 'created_at',   label: 'Oldest first' },
  ];

  readonly rejectionReasons = REJECTION_REASONS;

  // ── Selection ────────────────────────────────────────────────────
  readonly selectedIds = signal<ReadonlySet<string>>(new Set());

  /** Selected on the current page only — `selectedIds` is a session-wide
   *  set, but the "select all" checkbox is page-scoped so this computed
   *  asks "are all current-page suggestions in the set?". Recomputes
   *  only when suggestions OR selectedIds change. */
  readonly allSelected = computed(() => {
    const sugs = this.suggestions();
    const ids = this.selectedIds();
    return sugs.length > 0 && sugs.every(s => ids.has(s.suggestion_id));
  });

  readonly someSelected = computed(() => this.selectedIds().size > 0 && !this.allSelected());

  /** Phase SR — computed helper the template reads to decide which
   *  region to render. Mirrors the service but honours the session
   *  override flag. */
  readonly isReadyForSuggestions = computed(() => this.gateOverride() || this.readiness.ready());

  // ── Lifecycle ────────────────────────────────────────────────────

  ngOnInit(): void {
    // Phase SR — kick the readiness service. Idempotent; safe even if
    // some other page already started it.
    this.readiness.start();
    this.load();
  }

  /** Phase SR — operator-pressed "Show me anyway". A future Ops Feed
   *  emitter will replace the snackbar with a structured event. */
  onReadinessOverride(): void {
    this.gateOverride.set(true);
    this.snack.open(
      'Showing suggestions with stale prerequisites — results may be inaccurate.',
      'OK',
      { duration: 5000 },
    );
  }

  load(): void {
    this.loading.set(true);
    const filters: SuggestionFilters = {
      status: this.statusFilter,
      search: this.searchQuery,
      ordering: this.sortBy,
      page: this.page(),
      same_silo: this.sameSiloOnly,
    };
    this.svc.list(filters).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.suggestions.set(res.results);
        this.totalCount.set(res.count);
        this.loading.set(false);
        this.clearSelection();
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('Failed to load suggestions', 'Dismiss', { duration: 4000 });
      },
    });
  }

  // ── Filter handlers ──────────────────────────────────────────────

  setStatus(value: string): void {
    this.statusFilter = value;
    this.page.set(1);
    this.load();
  }

  onSearch(): void {
    this.page.set(1);
    this.load();
  }

  onSortChange(): void {
    this.page.set(1);
    this.load();
  }

  toggleSameSiloOnly(): void {
    this.page.set(1);
    this.load();
  }

  onPageChange(evt: PageEvent): void {
    this.page.set(evt.pageIndex + 1);
    this.load();
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.page.set(1);
    this.load();
  }

  // ── Selection ────────────────────────────────────────────────────

  toggleSelect(id: string): void {
    // Immutable Set update so the signal observes a new reference and
    // OnPush re-evaluates `allSelected` / `someSelected` computeds.
    this.selectedIds.update(curr => {
      const next = new Set(curr);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  toggleSelectAll(): void {
    if (this.allSelected()) {
      this.clearSelection();
    } else {
      const next = new Set(this.selectedIds());
      for (const s of this.suggestions()) {
        next.add(s.suggestion_id);
      }
      this.selectedIds.set(next);
    }
  }

  /** Template-side helper for the batch-bar's clear button — the
   *  previous inline `(click)="selectedIds.clear()"` doesn't compile
   *  against an immutable signal. */
  clearSelection(): void {
    this.selectedIds.set(new Set());
  }

  isSelected(id: string): boolean {
    return this.selectedIds().has(id);
  }

  // ── Quick actions (inline) ────────────────────────────────────────

  quickApprove(s: Suggestion, event: Event): void {
    event.stopPropagation();
    this.svc.approve(s.suggestion_id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (updated) => {
        this.replaceSuggestion(updated);
        this.snack.open('Approved', undefined, { duration: 2000 });
      },
      error: () => this.snack.open('Failed to approve', 'Dismiss', { duration: 4000 }),
    });
  }

  quickReject(s: Suggestion, reason: string, event: Event): void {
    event.stopPropagation();
    this.svc.reject(s.suggestion_id, reason).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (updated) => {
        this.replaceSuggestion(updated);
        this.snack.open('Rejected', undefined, { duration: 2000 });
      },
      error: () => this.snack.open('Failed to reject', 'Dismiss', { duration: 4000 }),
    });
  }

  // ── Batch actions ────────────────────────────────────────────────

  batchApprove(): void {
    const ids = [...this.selectedIds()];
    if (!ids.length) return;
    if (!confirm(`Approve ${ids.length} suggestion(s)?`)) return;
    this.svc.batchAction('approve', ids).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ updated }) => {
        this.snack.open(`Approved ${updated} suggestions`, undefined, { duration: 3000 });
        this.load();
      },
      error: () => this.snack.open('Batch approve failed', 'Dismiss', { duration: 4000 }),
    });
  }

  batchReject(reason: string): void {
    const ids = [...this.selectedIds()];
    if (!ids.length) return;
    if (!confirm(`Reject ${ids.length} suggestion(s)?`)) return;
    this.svc.batchAction('reject', ids, reason).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
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

    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        if (result) {
          this.replaceSuggestion(result.suggestion);
          const msgs: Record<string, string> = {
            approved: 'Suggestion approved',
            rejected: 'Suggestion rejected',
            applied:  'Marked as applied',
          };
          this.snack.open(msgs[result.action] ?? 'Saved', undefined, { duration: 2500 });
        }
      },
      error: () => this.snack.open('Dialog error', 'Dismiss', { duration: 4000 }),
    });
  }

  // ── Pipeline trigger ─────────────────────────────────────────────

  runPipeline(): void {
    const ref = this.dialog.open<
      RunPipelineDialogComponent,
      void,
      RunPipelineDialogResult | null
    >(RunPipelineDialogComponent, { width: '420px' });

    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe((result) => {
      if (!result) return;
      this.startingPipeline.set(true);
      this.svc.startPipeline(result.rerunMode).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (run) => {
          this.startingPipeline.set(false);
          this.snack.open(
            `Pipeline started (run ${run.run_id.slice(0, 8)})`,
            'Dismiss',
            { duration: 5000 }
          );
        },
        error: () => {
          this.startingPipeline.set(false);
          this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
        },
      });
    });
  }

  // ── Template helpers ─────────────────────────────────────────────

  scoreColor(score: number): string {
    if (score >= 0.75) return 'high';
    if (score >= 0.5)  return 'medium';
    return 'low';
  }

  /** Days since suggestion was created — for aging indicator. */
  daysWaiting(createdAt: string): number {
    const diff = Date.now() - new Date(createdAt).getTime();
    return Math.floor(diff / 86_400_000);
  }

  /** Aging severity for visual indicator. */
  agingLevel(createdAt: string): 'neutral' | 'amber' | 'red' {
    const days = this.daysWaiting(createdAt);
    if (days >= 30) return 'red';
    if (days >= 7) return 'amber';
    return 'neutral';
  }

  /** Map anchor_confidence to ConfidenceBadge level. */
  confidenceLevel(s: Suggestion): 'high' | 'medium' | 'low' | 'thin' {
    if (s.score_final < 0.5) return 'thin';
    if (s.anchor_confidence === 'strong') return 'high';
    if (s.anchor_confidence === 'weak') return 'medium';
    return 'low';
  }

  /** Whether this suggestion needs human judgment. */
  needsHumanJudgment(s: Suggestion): boolean {
    return (s.score_final >= 0.5 && s.score_final <= 0.65) ||
           s.anchor_confidence === 'none' ||
           (s.anchor_confidence === 'weak' && s.score_final < 0.55);
  }

  siloLabel(name: string): string {
    return name || 'Unassigned';
  }

  trackById(_: number, s: Suggestion): string {
    return s.suggestion_id;
  }

  /**
   * Replace a single suggestion in the page list. If the status changed
   * AND we're filtering by a non-"all" status, reload — the suggestion
   * has either dropped out of the filter (e.g. pending → approved while
   * viewing pending) or its position in the page may have shifted.
   * Otherwise patch in place via signal `.update()`.
   */
  private replaceSuggestion(updated: { suggestion_id: string; status: string } & Partial<Suggestion>): void {
    if (this.statusFilter !== 'all') {
      const current = this.suggestions().find(s => s.suggestion_id === updated.suggestion_id);
      if (current && updated.status !== this.statusFilter) {
        this.load();
        return;
      }
    }
    this.suggestions.update(arr =>
      arr.map(s => s.suggestion_id === updated.suggestion_id ? { ...s, ...updated } : s),
    );
  }
}
