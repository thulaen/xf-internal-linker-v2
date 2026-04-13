import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

export interface FunnelStage {
  stage: string;
  count: number;
  drop_reason?: string;
}

@Component({
  selector: 'app-suggestion-funnel',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="suggestion-funnel">
      <mat-card-header>
        <mat-icon mat-card-avatar>filter_alt</mat-icon>
        <mat-card-title>Suggestion Funnel</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (funnel.length === 0) {
          <p class="no-data">No funnel data yet. Run the pipeline to see where candidates drop off.</p>
        } @else {
          <div class="funnel-container">
            @for (stage of funnel; track stage.stage) {
              <div class="funnel-stage">
                <div class="stage-bar" [style.width.%]="barWidth(stage.count)">
                  <span class="stage-count">{{ stage.count }}</span>
                </div>
                <div class="stage-meta">
                  <span class="stage-name">{{ stage.stage }}</span>
                  @if (stage.drop_reason) {
                    <span class="stage-drop"
                          [matTooltip]="stage.drop_reason">
                      <mat-icon class="drop-icon">arrow_downward</mat-icon>
                      {{ stage.drop_reason }}
                    </span>
                  }
                </div>
              </div>
            }
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .no-data { font-size: 13px; color: var(--color-text-secondary); margin: 0; }
    .funnel-container { display: flex; flex-direction: column; gap: var(--space-sm); }
    .funnel-stage { display: flex; flex-direction: column; gap: var(--space-xs); }
    .stage-bar {
      min-width: 48px; height: 32px;
      background: var(--color-blue-50);
      border-radius: var(--radius-sm);
      display: flex; align-items: center;
      padding: 0 var(--space-sm);
      transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .stage-count { font-size: 13px; font-weight: 600; color: var(--color-primary); }
    .stage-meta { display: flex; align-items: center; gap: var(--space-sm); }
    .stage-name { font-size: 12px; font-weight: 500; color: var(--color-text-primary); }
    .stage-drop {
      font-size: 11px; color: var(--color-text-muted);
      display: flex; align-items: center; gap: 2px;
      cursor: help;
    }
    .drop-icon { font-size: 14px; width: 14px; height: 14px; color: var(--color-warning); }
  `],
})
export class SuggestionFunnelComponent {
  @Input() funnel: FunnelStage[] = [];

  barWidth(count: number): number {
    const max = this.funnel.reduce((m, s) => Math.max(m, s.count), 1);
    return Math.max((count / max) * 100, 8);
  }
}
