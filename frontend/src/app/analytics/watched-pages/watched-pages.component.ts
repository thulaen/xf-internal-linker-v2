import { Component, ChangeDetectionStrategy, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { DatePipe } from '@angular/common';
import { catchError, of } from 'rxjs';

interface WatchedPage {
  id: number; content_item_id: number; title: string;
  url: string; notes: string; added_at: string;
}

@Component({
  selector: 'app-watched-pages',
  standalone: true,
  imports: [MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatTooltipModule, MatSnackBarModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading) {
      <div class="loading-wrap"><mat-spinner diameter="48"></mat-spinner></div>
    } @else if (!pages.length) {
      <p class="empty-hint">You are not watching any pages yet. Add pages from the Under-Linked tab.</p>
    } @else {
      <div class="watch-list">
        @for (page of pages; track page.id) {
          <mat-card class="watch-card" appearance="outlined">
            <mat-card-content class="watch-row">
              <div class="watch-info">
                <a [href]="page.url" target="_blank" rel="noopener"
                  class="watch-title" [matTooltip]="page.url">{{ page.title }}</a>
                <div class="watch-meta">
                  @if (page.notes) {
                    <span class="watch-notes">{{ page.notes }}</span>
                    <span class="separator"> -- </span>
                  }
                  <span class="watch-date">Added {{ page.added_at | date:'mediumDate' }}</span>
                </div>
              </div>
              <button mat-icon-button (click)="remove(page)"
                [disabled]="removingId === page.id"
                matTooltip="Remove from watchlist" aria-label="Remove from watchlist">
                <mat-icon>close</mat-icon>
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
    .empty-hint { color: var(--color-text-muted); text-align: center; padding: var(--space-xl); }
    .watch-list { display: flex; flex-direction: column; gap: var(--space-sm); }
    .watch-card { border: var(--card-border); box-shadow: none; }
    .watch-row {
      display: flex; align-items: center; gap: var(--space-md);
      padding: var(--space-md);
    }
    .watch-info { flex: 1; min-width: 0; }
    .watch-title { font-weight: 500; color: var(--color-primary); text-decoration: none; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .watch-title:hover { text-decoration: underline; }
    .watch-meta { margin-top: var(--space-xs); font-size: 12px; color: var(--color-text-muted); display: flex; align-items: center; gap: var(--space-xs); flex-wrap: wrap; }
    .watch-notes { color: var(--color-text-secondary); }
    .separator { color: var(--color-text-disabled); }
    .watch-date { white-space: nowrap; }
  `],
})
export class WatchedPagesComponent implements OnInit {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);
  pages: WatchedPage[] = [];
  loading = true;
  removingId: number | null = null;

  ngOnInit(): void {
    this.http.get<WatchedPage[]>('/api/analytics/watched-pages/')
      .pipe(catchError(() => of([])), takeUntilDestroyed(this.destroyRef))
      .subscribe(data => { this.pages = data; this.loading = false; });
  }

  remove(page: WatchedPage): void {
    this.removingId = page.id;
    this.http.delete(`/api/analytics/watched-pages/${page.id}/`)
      .pipe(
        catchError(() => { this.snack.open('Could not remove page.', 'Dismiss', { duration: 3000 }); return of(null); }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(res => {
        this.removingId = null;
        if (res !== null) {
          this.pages = this.pages.filter(p => p.id !== page.id);
          this.snack.open(`"${page.title}" removed.`, undefined, { duration: 2500 });
        }
      });
  }
}
