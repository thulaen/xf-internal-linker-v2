import { Component, ChangeDetectionStrategy, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { DecimalPipe } from '@angular/common';
import { catchError, of } from 'rxjs';

interface MismatchRow {
  query: string;
  landing_page_id: number;
  landing_page_title: string;
  clicks: number;
  impressions: number;
  avg_position: number;
}

@Component({
  selector: 'app-query-mismatch',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatProgressSpinnerModule, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading) {
      <div class="loading-wrap"><mat-spinner diameter="48"></mat-spinner></div>
    } @else if (!rows.length) {
      <p class="empty-hint">No query mismatches detected.</p>
    } @else {
      <div class="mismatch-list">
        @for (row of rows; track row.query + row.landing_page_id) {
          <mat-card class="mismatch-card" appearance="outlined">
            <mat-card-content class="mismatch-row">
              <mat-icon class="mismatch-icon">swap_horiz</mat-icon>
              <div class="mismatch-body">
                <p class="hint-text">
                  People search "<strong>{{ row.query }}</strong>" but land on
                  "<strong>{{ row.landing_page_title }}</strong>."
                </p>
                <div class="mismatch-stats">
                  <span>{{ row.clicks | number }} clicks</span>
                  <span class="separator"> -- </span>
                  <span>{{ row.impressions | number }} impressions</span>
                  <span class="separator"> -- </span>
                  <span>Avg position: {{ row.avg_position | number:'1.1-1' }}</span>
                </div>
              </div>
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    :host { display: block; }
    .loading-wrap { display: flex; justify-content: center; padding: var(--space-xl); }
    .empty-hint { color: var(--color-text-muted); text-align: center; padding: var(--space-xl); }
    .mismatch-list { display: flex; flex-direction: column; gap: var(--space-sm); }
    .mismatch-card { border: var(--card-border); box-shadow: none; }
    .mismatch-row {
      display: flex; align-items: flex-start; gap: var(--space-md);
      padding: var(--space-md);
    }
    .mismatch-icon { color: var(--color-primary); flex-shrink: 0; margin-top: var(--space-xs); }
    .mismatch-body { flex: 1; min-width: 0; }
    .hint-text {
      color: var(--color-text-primary); margin: 0 0 var(--space-xs); font-size: 13px;
      line-height: 1.5;
    }
    .hint-text strong { font-weight: 600; }
    .mismatch-stats {
      display: flex; align-items: center; gap: var(--space-xs);
      font-size: 12px; color: var(--color-text-muted); flex-wrap: wrap;
    }
    .separator { color: var(--color-text-disabled); }
  `],
})
export class QueryMismatchComponent implements OnInit {
  private http = inject(HttpClient);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);
  rows: MismatchRow[] = [];
  loading = true;

  ngOnInit(): void {
    this.http.get<MismatchRow[]>('/api/analytics/query-mismatch/')
      .pipe(catchError(() => of([])), takeUntilDestroyed(this.destroyRef))
      .subscribe(data => { this.rows = data; this.loading = false; });
  }
}
