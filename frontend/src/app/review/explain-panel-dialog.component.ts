import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  SuggestionExplanation,
  SuggestionFeatureContribution,
  SuggestionService,
} from './suggestion.service';

export interface ExplainPanelData {
  suggestionId: string;
}

/**
 * W4 — pick #47 Explain panel.
 *
 * Renders the SHAP-style per-feature attributions returned by
 * `GET /api/suggestions/<id>/explain/`. The contributions are sorted
 * server-side by absolute magnitude, so the strongest drivers
 * (positive or negative) sit at the top of the list. Each row uses a
 * `mat-progress-bar` whose width represents the contribution
 * magnitude relative to the largest in the set, and whose colour is
 * green for positive contributions, red for negative.
 *
 * The Platt-calibrated probability (W3a) appears as a chip at the top
 * when calibration data is available. Cold-start installs see "—"
 * instead of a fake percentage.
 */
@Component({
  selector: 'app-explain-panel-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressBarModule,
    MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">insights</mat-icon>
      Why this score?
    </h2>

    <mat-dialog-content class="explain-content">
      <div *ngIf="loading" class="loading">
        <mat-progress-bar mode="indeterminate"></mat-progress-bar>
        <span class="loading-text">Computing feature attributions…</span>
      </div>

      <div *ngIf="error" class="error">
        <mat-icon>error_outline</mat-icon>
        <span>{{ error }}</span>
      </div>

      <ng-container *ngIf="explanation && !loading">
        <div class="summary">
          <div class="summary-row">
            <span class="label">Predicted score</span>
            <span class="value">{{ explanation.predicted_value | number: '1.3-3' }}</span>
          </div>
          <div class="summary-row">
            <span class="label">Baseline (neutral)</span>
            <span class="value">{{ explanation.baseline | number: '1.3-3' }}</span>
          </div>
          <div class="summary-row" *ngIf="explanation.calibrated_probability !== null">
            <span class="label">Calibrated probability</span>
            <span class="value">
              {{ (explanation.calibrated_probability ?? 0) * 100 | number: '1.0-1' }}%
            </span>
          </div>
          <div class="summary-row" *ngIf="explanation.calibrated_probability === null">
            <span class="label">Calibrated probability</span>
            <span class="value muted" matTooltip="Not enough review history yet">—</span>
          </div>
          <div class="summary-row method">
            <span class="label">Method</span>
            <span class="value">{{ explanation.method }}</span>
          </div>
        </div>

        <h3 class="contributions-title">Feature contributions</h3>

        <div class="contributions">
          <div
            *ngFor="let c of explanation.contributions"
            class="contribution-row"
          >
            <div class="contribution-header">
              <span class="feature-name">{{ c.feature_name }}</span>
              <span
                class="contribution-value"
                [class.positive]="c.shap_value > 0"
                [class.negative]="c.shap_value < 0"
              >
                {{ c.shap_value > 0 ? '+' : '' }}{{ c.shap_value | number: '1.3-3' }}
              </span>
            </div>
            <div class="contribution-bar">
              <mat-progress-bar
                mode="determinate"
                [value]="barMagnitude(c)"
                [color]="c.shap_value >= 0 ? 'primary' : 'warn'"
              ></mat-progress-bar>
            </div>
            <div class="contribution-meta">
              raw value {{ c.value | number: '1.3-3' }}
            </div>
          </div>
        </div>
      </ng-container>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="null">Close</button>
    </mat-dialog-actions>
  `,
  styles: [
    `
      :host {
        display: block;
      }
      .title-icon {
        vertical-align: middle;
        margin-right: 8px;
      }
      .explain-content {
        min-width: 480px;
        max-width: 720px;
      }
      .loading {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 24px 0;
      }
      .loading-text {
        text-align: center;
        font-size: 13px;
        color: var(--color-text-secondary, #5f6368);
      }
      .error {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 16px;
        background: var(--color-warning-bg, #fef7e0);
        border-radius: 8px;
      }
      .summary {
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 16px 0;
      }
      .summary-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 13px;
      }
      .summary-row .label {
        color: var(--color-text-secondary, #5f6368);
      }
      .summary-row .value {
        font-weight: 500;
        font-variant-numeric: tabular-nums;
      }
      .summary-row .value.muted {
        color: var(--color-text-secondary, #5f6368);
      }
      .summary-row.method .value {
        font-family: 'JetBrains Mono', 'Consolas', monospace;
        font-size: 12px;
      }
      .contributions-title {
        font-size: 14px;
        font-weight: 500;
        margin: 16px 0 12px;
      }
      .contributions {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .contribution-row {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .contribution-header {
        display: flex;
        justify-content: space-between;
        font-size: 13px;
      }
      .contribution-header .feature-name {
        font-weight: 500;
      }
      .contribution-value {
        font-variant-numeric: tabular-nums;
        font-weight: 500;
      }
      .contribution-value.positive {
        color: #1e8e3e;
      }
      .contribution-value.negative {
        color: #d93025;
      }
      .contribution-meta {
        font-size: 11px;
        color: var(--color-text-secondary, #5f6368);
      }
    `,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ExplainPanelDialogComponent implements OnInit {
  explanation: SuggestionExplanation | null = null;
  loading = true;
  error = '';

  readonly data: ExplainPanelData = inject(MAT_DIALOG_DATA);
  private dialogRef = inject(MatDialogRef) as MatDialogRef<ExplainPanelDialogComponent>;
  private svc = inject(SuggestionService);
  private destroyRef = inject(DestroyRef);
  private cdr = inject(ChangeDetectorRef);

  /** Largest absolute SHAP magnitude in the explanation — used to
   *  scale every bar to the visible 0-100 progress-bar range. */
  private maxMagnitude = 0;

  ngOnInit(): void {
    this.svc
      .explain(this.data.suggestionId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (e) => {
          this.explanation = e;
          this.maxMagnitude = Math.max(
            ...e.contributions.map((c) => Math.abs(c.shap_value)),
            1e-9, // never divide by zero
          );
          this.loading = false;
          this.cdr.markForCheck();
        },
        error: (err) => {
          this.error =
            err?.error?.detail ??
            'Failed to load explanation — see browser console for details.';
          this.loading = false;
          this.cdr.markForCheck();
        },
      });
  }

  /** Map a contribution's |shap_value| to a 0-100 progress-bar value. */
  barMagnitude(c: SuggestionFeatureContribution): number {
    if (this.maxMagnitude <= 0) return 0;
    return Math.min(100, (Math.abs(c.shap_value) / this.maxMagnitude) * 100);
  }
}
