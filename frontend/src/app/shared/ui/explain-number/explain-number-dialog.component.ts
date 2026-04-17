import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { ExplainNumberInput } from './explain-number.types';

/**
 * Phase D2 / Gap 77 — "Explain this number" modal body.
 *
 * Pure presentation — receives an ExplainNumberInput via MAT_DIALOG_DATA
 * and renders the derivation, formula, inputs, and a drill-in link.
 */
@Component({
  selector: 'app-explain-number-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="end-icon">calculate</mat-icon>
      Explain this number
    </h2>
    <mat-dialog-content>
      <div class="end-headline">
        <span class="end-label">{{ data.label }}</span>
        <span class="end-value">{{ data.value }}</span>
      </div>
      <p class="end-derivation">{{ data.derivation }}</p>

      @if (data.inputs && data.inputs.length > 0) {
        <h3 class="end-sub">Inputs</h3>
        <dl class="end-inputs">
          @for (i of data.inputs; track i.name) {
            <div>
              <dt>{{ i.name }}</dt>
              <dd>{{ i.value }}</dd>
            </div>
          }
        </dl>
      }

      @if (data.formula) {
        <h3 class="end-sub">Formula</h3>
        <pre class="end-formula"><code>{{ data.formula }}</code></pre>
      }

      @if (data.generatedAt) {
        <p class="end-freshness">
          <mat-icon>schedule</mat-icon>
          Computed at {{ data.generatedAt | date:'medium' }}.
        </p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Close</button>
      @if (data.drillRoute) {
        <a
          mat-raised-button
          color="primary"
          [routerLink]="data.drillRoute"
          mat-dialog-close
        >
          {{ data.drillLabel || 'Drill in' }}
          <mat-icon iconPositionEnd>arrow_forward</mat-icon>
        </a>
      }
    </mat-dialog-actions>
  `,
  styles: [`
    .end-icon {
      vertical-align: middle;
      margin-right: 6px;
      color: var(--color-primary);
    }
    .end-headline {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 16px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
      margin-bottom: 16px;
    }
    .end-label {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .end-value {
      font-size: 28px;
      font-weight: 500;
      color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
    }
    .end-derivation {
      margin: 0 0 16px;
      font-size: 14px;
      line-height: 1.55;
      color: var(--color-text-primary);
    }
    .end-sub {
      margin: 16px 0 8px;
      font-size: 12px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--color-text-secondary);
    }
    .end-inputs {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 0;
    }
    .end-inputs > div {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      padding: 6px 12px;
      border-radius: 4px;
    }
    .end-inputs > div:nth-child(odd) {
      background: var(--color-bg-faint);
    }
    .end-inputs dt {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .end-inputs dd {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
    }
    .end-formula {
      margin: 0;
      padding: 12px;
      background: var(--color-bg-faint);
      border-radius: var(--card-border-radius, 8px);
      font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
      font-size: 12px;
      color: var(--color-text-primary);
      overflow-x: auto;
    }
    .end-freshness {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin: 16px 0 0;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .end-freshness mat-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
  `],
})
export class ExplainNumberDialogComponent {
  readonly data = inject<ExplainNumberInput>(MAT_DIALOG_DATA);
  readonly dialogRef = inject(MatDialogRef<ExplainNumberDialogComponent>);
}
