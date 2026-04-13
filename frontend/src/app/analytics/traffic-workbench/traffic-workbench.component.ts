import { Component, ChangeDetectionStrategy, Input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { DecimalPipe } from '@angular/common';
import { ConfidenceBadgeComponent } from '../../shared/confidence-badge/confidence-badge.component';

const WOW_THRESHOLD = 30;

@Component({
  selector: 'app-traffic-workbench',
  standalone: true,
  imports: [MatCardModule, MatIconModule, DecimalPipe, ConfidenceBadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!filteredRows.length) {
      <p class="empty-hint">No pages with more than 30% week-over-week traffic change.</p>
    } @else {
      <div class="workbench-list">
        @for (row of filteredRows; track row.title) {
          <mat-card class="workbench-card" appearance="outlined">
            <mat-card-content class="workbench-row">
              <mat-icon [class]="row.change_pct >= 0 ? 'arrow-up' : 'arrow-down'">
                {{ row.change_pct >= 0 ? 'trending_up' : 'trending_down' }}
              </mat-icon>
              <span class="row-title">{{ row.title }}</span>
              <span [class]="row.change_pct >= 0 ? 'delta-pos' : 'delta-neg'">
                {{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct | number:'1.1-1' }}%
              </span>
              <app-confidence-badge [level]="row.confidence ?? 'thin'"></app-confidence-badge>
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    :host { display: block; }
    .empty-hint { color: var(--color-text-muted); text-align: center; padding: var(--space-xl); }
    .workbench-list { display: flex; flex-direction: column; gap: var(--space-sm); }
    .workbench-card { border: var(--card-border); box-shadow: none; }
    .workbench-row {
      display: flex; align-items: center; gap: var(--space-md);
      padding: var(--space-md);
    }
    .arrow-up { color: var(--color-success); }
    .arrow-down { color: var(--color-error); }
    .row-title {
      flex: 1; font-weight: 500; color: var(--color-text-primary);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .delta-pos { color: var(--color-success); font-weight: 500; white-space: nowrap; }
    .delta-neg { color: var(--color-error); font-weight: 500; white-space: nowrap; }
  `],
})
export class TrafficWorkbenchComponent {
  @Input() set telemetryData(data: any[]) {
    this._data = data ?? [];
    this.filteredRows = this._data
      .filter(r => Math.abs(r.change_pct ?? 0) > WOW_THRESHOLD)
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct));
  }

  private _data: any[] = [];
  filteredRows: any[] = [];
}
