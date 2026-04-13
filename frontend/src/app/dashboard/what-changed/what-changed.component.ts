import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

export interface WhatChangedData {
  new_suggestions: number;
  reviewed: number;
  items_synced: number;
  pipeline_runs: number;
  autotuner_outcome?: string;
}

@Component({
  selector: 'app-what-changed',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, MatButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="what-changed">
      <mat-card-header>
        <mat-icon mat-card-avatar>update</mat-icon>
        <mat-card-title>What Changed (Last 24h)</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="metrics-row">
          <div class="metric-box">
            <span class="metric-value">{{ changes.new_suggestions }}</span>
            <span class="metric-label">New Suggestions</span>
          </div>
          <div class="metric-box">
            <span class="metric-value">{{ changes.reviewed }}</span>
            <span class="metric-label">Reviewed</span>
          </div>
          <div class="metric-box">
            <span class="metric-value">{{ changes.items_synced }}</span>
            <span class="metric-label">Items Synced</span>
          </div>
          <div class="metric-box">
            <span class="metric-value">{{ changes.pipeline_runs }}</span>
            <span class="metric-label">Pipeline Runs</span>
          </div>
        </div>
        @if (changes.autotuner_outcome) {
          <div class="autotuner-row">
            <mat-icon class="autotuner-icon">auto_fix_high</mat-icon>
            <span class="autotuner-text">Auto-tuner: {{ changes.autotuner_outcome }}</span>
            <a mat-button routerLink="/settings" fragment="ranking-weights">View Settings</a>
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .metrics-row {
      display: flex; gap: var(--space-md);
      flex-wrap: wrap;
    }
    .metric-box {
      flex: 1; min-width: 100px;
      display: flex; flex-direction: column; align-items: center;
      padding: var(--space-md);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      text-align: center;
    }
    .metric-value {
      font-size: 24px; font-weight: 600;
      color: var(--color-primary);
    }
    .metric-label {
      font-size: 12px; color: var(--color-text-muted);
      margin-top: var(--space-xs);
    }
    .autotuner-row {
      display: flex; align-items: center; gap: var(--space-sm);
      margin-top: var(--space-md);
      padding: var(--space-sm) var(--space-md);
      background: var(--color-blue-50);
      border-radius: var(--radius-sm);
    }
    .autotuner-icon { color: var(--color-primary); }
    .autotuner-text { flex: 1; font-size: 13px; color: var(--color-text-primary); }
  `],
})
export class WhatChangedComponent {
  @Input() changes: WhatChangedData = {
    new_suggestions: 0, reviewed: 0, items_synced: 0, pipeline_runs: 0,
  };
}
