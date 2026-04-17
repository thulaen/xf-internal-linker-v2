import { Component, ChangeDetectionStrategy, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { DatePipe } from '@angular/common';
import { catchError, of } from 'rxjs';
import { ConfidenceBadgeComponent } from '../../shared/confidence-badge/confidence-badge.component';

interface ImpactEntry {
  suggestion_id: string; metric_type: string; before_value: number; after_value: number;
  delta_percent: number; attribution_model: string; confidence: 'high' | 'medium' | 'low' | 'thin';
  is_conclusive: boolean; control_match_count: number; created_at: string;
}

@Component({
  selector: 'app-impact-diary',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatChipsModule, MatProgressSpinnerModule, DatePipe, ConfidenceBadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading) {
      <div class="loading-wrap"><mat-spinner diameter="48"></mat-spinner></div>
    } @else if (!entries.length) {
      <p class="empty-hint">No impact reports recorded yet.</p>
    } @else {
      <div class="timeline">
        @for (entry of entries; track entry.suggestion_id + entry.created_at) {
          <mat-card class="timeline-card" appearance="outlined">
            <mat-card-content class="entry-row">
              <mat-icon [class]="entry.delta_percent >= 0 ? 'arrow-up' : 'arrow-down'">
                {{ entry.delta_percent >= 0 ? 'arrow_upward' : 'arrow_downward' }}
              </mat-icon>
              <div class="entry-body">
                <span class="metric-label">{{ entry.metric_type }}</span>
                <span class="separator"> -- </span>
                <span [class]="entry.delta_percent >= 0 ? 'delta-pos' : 'delta-neg'">
                  {{ entry.delta_percent >= 0 ? '+' : '' }}{{ entry.delta_percent.toFixed(1) }}%
                </span>
                <span class="separator"> -- </span>
                <span class="model-label">{{ entry.attribution_model }}</span>
              </div>
              <div class="entry-meta">
                @if (!entry.is_conclusive) {
                  <mat-chip class="inconclusive-chip" disableRipple>Not enough data yet</mat-chip>
                } @else {
                  <app-confidence-badge [level]="entry.confidence"></app-confidence-badge>
                }
                <span class="date-label">{{ entry.created_at | date:'mediumDate' }}</span>
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
    .timeline { display: flex; flex-direction: column; gap: var(--space-sm); }
    .timeline-card { border: var(--card-border); box-shadow: none; }
    .entry-row {
      display: flex; align-items: center; gap: var(--space-md);
      padding: var(--space-md);
    }
    .arrow-up { color: var(--color-success); }
    .arrow-down { color: var(--color-error); }
    .entry-body { flex: 1; display: flex; align-items: center; gap: var(--space-xs); flex-wrap: wrap; }
    .metric-label { font-weight: 500; color: var(--color-text-primary); }
    .separator { color: var(--color-text-muted); }
    .delta-pos { color: var(--color-success); font-weight: 500; }
    .delta-neg { color: var(--color-error); font-weight: 500; }
    .model-label { color: var(--color-text-secondary); font-size: 12px; }
    .entry-meta { display: flex; align-items: center; gap: var(--space-sm); flex-shrink: 0; }
    .date-label { color: var(--color-text-muted); font-size: 12px; white-space: nowrap; }
    .inconclusive-chip {
      --mdc-chip-elevated-container-color: var(--color-bg-faint);
      --mdc-chip-label-text-color: var(--color-text-muted);
      font-size: 11px; height: 24px;
    }
  `],
})
export class ImpactDiaryComponent implements OnInit {
  private http = inject(HttpClient);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);
  entries: ImpactEntry[] = [];
  loading = true;

  ngOnInit(): void {
    this.http.get<ImpactEntry[]>('/api/analytics/impacts/')
      .pipe(catchError(() => of([])), takeUntilDestroyed(this.destroyRef))
      .subscribe(data => { this.entries = data; this.loading = false; });
  }
}
