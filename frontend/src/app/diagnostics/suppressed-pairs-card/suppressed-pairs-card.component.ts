import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
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
    MatTooltipModule,
  ],
  templateUrl: './suppressed-pairs-card.component.html',
  styleUrls: ['./suppressed-pairs-card.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SuppressedPairsCardComponent implements OnInit {
  private diagnosticsService = inject(DiagnosticsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  // All render-affecting state lives in signals so OnPush change
  // detection picks up every mutation automatically — no markForCheck
  // sprinkled through subscribe callbacks. See AGENT-HANDOFF.md
  // (signals migration recipe, 2026-04-26).
  readonly counters = signal<SuppressedPairsDiagnostics | null>(null);
  readonly expanded = signal(false);
  readonly list = signal<SuppressedPairListItem[] | null>(null);
  readonly listLoading = signal(false);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly total = signal(0);
  readonly clearingId = signal<number | null>(null);

  // Derived value — recomputes only when its inputs change. Replaces
  // the previous `get pageCount()` getter, which re-evaluated on every
  // template binding read regardless of input churn.
  readonly pageCount = computed(() => {
    const size = this.pageSize();
    if (size <= 0) return 1;
    return Math.max(1, Math.ceil(this.total() / size));
  });

  ngOnInit(): void {
    this.loadCounters();
  }

  private loadCounters(): void {
    this.diagnosticsService
      .getSuppressedPairs()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (counters) => this.counters.set(counters),
        error: () => this.counters.set(null),
      });
  }

  toggleList(): void {
    const next = !this.expanded();
    this.expanded.set(next);
    if (next && this.list() === null) {
      this.loadList();
    }
  }

  loadList(page: number = this.page()): void {
    this.listLoading.set(true);
    this.diagnosticsService
      .getSuppressedPairsList(page, this.pageSize())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.list.set(res.items);
          this.total.set(res.total);
          this.page.set(res.page);
          this.listLoading.set(false);
        },
        error: () => {
          this.listLoading.set(false);
          this.snack.open('Could not load suppressed pairs.', 'Dismiss', { duration: 4000 });
        },
      });
  }

  onClear(item: SuppressedPairListItem): void {
    const ok = window.confirm(
      `Clear suppression for "${item.host.title}" → "${item.destination.title}"?\n\n` +
        `This deletes the row and writes an audit entry. A future rejection starts a fresh 90-day window.`,
    );
    if (!ok) return;

    this.clearingId.set(item.id);
    this.diagnosticsService
      .clearSuppressedPair(item.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.clearingId.set(null);
          this.list.update((curr) => (curr ?? []).filter((p) => p.id !== item.id));
          this.total.update((t) => Math.max(0, t - 1));
          this.loadCounters();
          this.snack.open(
            `Suppression cleared for "${item.destination.title}".`,
            'Dismiss',
            { duration: 3000 },
          );
        },
        error: (err) => {
          this.clearingId.set(null);
          const detail = err?.error?.detail ?? 'Please refresh and try again.';
          this.snack.open(`Could not clear suppression: ${detail}`, 'Dismiss', { duration: 5000 });
        },
      });
  }

  goToPage(next: number): void {
    if (next < 1 || next > this.pageCount() || next === this.page()) return;
    this.loadList(next);
  }
}
