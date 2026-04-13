import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

export interface OpportunityPage {
  title: string;
  url: string;
  opportunity_score: number;
}

@Component({
  selector: 'app-top-opportunity-pages',
  standalone: true,
  imports: [DecimalPipe, MatCardModule, MatIconModule, MatTableModule, EmptyStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="top-opportunity-pages">
      <mat-card-header>
        <mat-icon mat-card-avatar>trending_up</mat-icon>
        <mat-card-title>Top Opportunity Pages</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (pages.length === 0) {
          <app-empty-state
            icon="insert_chart"
            heading="No opportunity data yet"
            body="Run the pipeline to discover pages with the most linking potential." />
        } @else {
          <table mat-table [dataSource]="pages" class="opp-table">
            <ng-container matColumnDef="title">
              <th mat-header-cell *matHeaderCellDef>Page</th>
              <td mat-cell *matCellDef="let row">
                <a class="page-link" [href]="row.url" target="_blank" rel="noopener">
                  {{ row.title }}
                </a>
              </td>
            </ng-container>
            <ng-container matColumnDef="opportunity_score">
              <th mat-header-cell *matHeaderCellDef>Score</th>
              <td mat-cell *matCellDef="let row">
                <span class="score-value">{{ row.opportunity_score | number:'1.0-1' }}</span>
              </td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
          </table>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .opp-table { width: 100%; }
    .page-link {
      color: var(--color-primary);
      text-decoration: none;
      font-size: 13px;
    }
    .page-link:hover { text-decoration: underline; }
    .score-value {
      font-weight: 600; font-size: 13px;
      color: var(--color-primary);
    }
    th.mat-mdc-header-cell {
      font-size: 12px; font-weight: 500;
      color: var(--color-text-muted);
    }
  `],
})
export class TopOpportunityPagesComponent {
  @Input() pages: OpportunityPage[] = [];
  readonly displayedColumns = ['title', 'opportunity_score'];
}
