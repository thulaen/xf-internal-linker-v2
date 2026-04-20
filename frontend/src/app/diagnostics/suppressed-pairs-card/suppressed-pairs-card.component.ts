import { Component, OnInit, inject, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  DiagnosticsService,
  SuppressedPairsDiagnostics,
  SuppressedPairListItem,
} from '../diagnostics.service';

/**
 * Phase 1v + Tier 2 slice 4 — the Diagnostics-page negative-memory card.
 * Owns the counter tiles (aggregate summary) AND the drilldown table with
 * per-row clear action. Self-contained: fetches its own data, writes its
 * own audit entries via the backend, renders its own snackbar feedback.
 */
@Component({
  selector: 'app-suppressed-pairs-card',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  templateUrl: './suppressed-pairs-card.component.html',
  styleUrls: ['./suppressed-pairs-card.component.scss'],
})
export class SuppressedPairsCardComponent implements OnInit {
  private diagnosticsService = inject(DiagnosticsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  counters: SuppressedPairsDiagnostics | null = null;

  expanded = false;
  list: SuppressedPairListItem[] | null = null;
  listLoading = false;
  page = 1;
  pageSize = 25;
  total = 0;
  clearingId: number | null = null;

  ngOnInit(): void {
    this.loadCounters();
  }

  private loadCounters(): void {
    this.diagnosticsService
      .getSuppressedPairs()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: counters => (this.counters = counters),
        error: () => (this.counters = null),
      });
  }

  toggleList(): void {
    this.expanded = !this.expanded;
    if (this.expanded && this.list === null) {
      this.loadList();
    }
  }

  loadList(page: number = this.page): void {
    this.listLoading = true;
    this.diagnosticsService
      .getSuppressedPairsList(page, this.pageSize)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.list = res.items;
          this.total = res.total;
          this.page = res.page;
          this.listLoading = false;
        },
        error: () => {
          this.listLoading = false;
          this.snack.open('Could not load suppressed pairs.', 'Dismiss', { duration: 4000 });
        },
      });
  }

  onClear(item: SuppressedPairListItem): void {
    const ok = window.confirm(
      `Clear suppression for "${item.host.title}" \u2192 "${item.destination.title}"?\n\n` +
        `This deletes the row and writes an audit entry. A future rejection starts a fresh 90-day window.`,
    );
    if (!ok) return;

    this.clearingId = item.id;
    this.diagnosticsService
      .clearSuppressedPair(item.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.clearingId = null;
          this.list = (this.list ?? []).filter(p => p.id !== item.id);
          this.total = Math.max(0, this.total - 1);
          this.loadCounters();
          this.snack.open(
            `Suppression cleared for "${item.destination.title}".`,
            'Dismiss',
            { duration: 3000 },
          );
        },
        error: err => {
          this.clearingId = null;
          const detail = err?.error?.detail ?? 'Please refresh and try again.';
          this.snack.open(`Could not clear suppression: ${detail}`, 'Dismiss', { duration: 5000 });
        },
      });
  }

  get pageCount(): number {
    if (this.pageSize <= 0) return 1;
    return Math.max(1, Math.ceil(this.total / this.pageSize));
  }

  goToPage(next: number): void {
    if (next < 1 || next > this.pageCount || next === this.page) return;
    this.loadList(next);
  }

  trackPair(_i: number, p: SuppressedPairListItem): number { return p.id; }
}
