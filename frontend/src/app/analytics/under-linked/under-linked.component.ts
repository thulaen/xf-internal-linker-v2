import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { catchError, of } from 'rxjs';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

interface GapRow {
  content_item_id: number; title: string; url: string;
  opportunity_score: number; incoming_link_count: number;
}

@Component({
  selector: 'app-under-linked',
  standalone: true,
  imports: [MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatSnackBarModule, EmptyStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading) {
      <div class="loading-wrap"><mat-spinner diameter="48"></mat-spinner></div>
    } @else if (!rows.length) {
      <app-empty-state icon="link_off" heading="No under-linked pages"
        body="All pages have adequate incoming links. Check back after your next import.">
      </app-empty-state>
    } @else {
      <div class="gap-list">
        @for (row of rows; track row.content_item_id) {
          <mat-card class="gap-card" appearance="outlined">
            <mat-card-content class="gap-row">
              <div class="gap-info">
                <span class="gap-title">{{ row.title }}</span>
                <div class="gap-meta">
                  <span class="link-count">{{ row.incoming_link_count }} incoming links</span>
                </div>
              </div>
              <div class="score-bar-wrap">
                <div class="score-bar" [style.width.%]="row.opportunity_score"></div>
                <span class="score-label">{{ row.opportunity_score.toFixed(0) }}%</span>
              </div>
              <button mat-stroked-button class="watch-btn" (click)="watch(row)"
                [disabled]="watchingId === row.content_item_id">
                <mat-icon>visibility</mat-icon> Watch
              </button>
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    :host { display: block; }
    .loading-wrap { display: flex; justify-content: center; padding: var(--space-xl); }
    .gap-list { display: flex; flex-direction: column; gap: var(--space-sm); }
    .gap-card { border: var(--card-border); box-shadow: none; }
    .gap-row {
      display: flex; align-items: center; gap: var(--space-md);
      padding: var(--space-md);
    }
    .gap-info { flex: 1; min-width: 0; }
    .gap-title { font-weight: 500; color: var(--color-text-primary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .gap-meta { margin-top: var(--space-xs); }
    .link-count { font-size: 12px; color: var(--color-text-muted); }
    .score-bar-wrap { width: 120px; display: flex; align-items: center; gap: var(--space-sm); }
    .score-bar { height: 8px; border-radius: var(--radius-sm); background: var(--color-primary); min-width: 4px; }
    .score-label { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; }
    .watch-btn { flex-shrink: 0; }
  `],
})
export class UnderLinkedComponent implements OnInit {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  rows: GapRow[] = [];
  loading = true;
  watchingId: number | null = null;

  ngOnInit(): void {
    this.http.get<GapRow[]>('/api/graph/gap-analysis/')
      .pipe(catchError(() => of([])))
      .subscribe(data => { this.rows = data; this.loading = false; });
  }

  watch(row: GapRow): void {
    this.watchingId = row.content_item_id;
    this.http.post('/api/analytics/watched-pages/', { content_item_id: row.content_item_id, notes: '' })
      .pipe(catchError(() => { this.snack.open('Could not add to watchlist.', 'Dismiss', { duration: 3000 }); return of(null); }))
      .subscribe(res => {
        this.watchingId = null;
        if (res) { this.snack.open(`"${row.title}" added to watchlist.`, undefined, { duration: 2500 }); }
      });
  }
}
