import { ChangeDetectionStrategy, Component, Input, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ExplainNumberDialogComponent } from './explain-number-dialog.component';
import { ExplainNumberInput } from './explain-number.types';

/**
 * Phase D2 / Gap 77 — "Explain this number" trigger button.
 *
 * Drop next to any displayed metric to give the user a one-click
 * reveal of the derivation:
 *
 *   <h2>
 *     Health Score: {{ score() }}
 *     <app-explain-number [data]="healthExplain" />
 *   </h2>
 *
 *   healthExplain: ExplainNumberInput = {
 *     label: 'Health Score',
 *     value: this.score(),
 *     derivation: 'Computed from system status, broken-link backlog, and unread urgent alerts.',
 *     formula: 'score = 100 - 30·downCount - 15·warningCount - 10·urgentAlerts - 5·floor(brokenLinks/50)',
 *     inputs: [...],
 *     drillRoute: '/health',
 *   };
 *
 * The button itself is a tiny calculator icon, so it doesn't compete
 * with the metric value visually.
 */
@Component({
  selector: 'app-explain-number',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <button
      mat-icon-button
      type="button"
      class="enb"
      matTooltip="Explain this number"
      [attr.aria-label]="'Explain ' + (data?.label || 'this number')"
      (click)="open()"
    >
      <mat-icon>calculate</mat-icon>
    </button>
  `,
  styles: [`
    .enb {
      width: 28px;
      height: 28px;
      line-height: 28px;
      vertical-align: middle;
    }
    .enb mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
      color: var(--color-text-secondary);
    }
    .enb:hover mat-icon { color: var(--color-primary); }
  `],
})
export class ExplainNumberComponent {
  private readonly dialog = inject(MatDialog);

  /** Required — every button must know what it explains. */
  @Input({ required: true }) data: ExplainNumberInput | null = null;

  open(): void {
    if (!this.data) return;
    this.dialog.open(ExplainNumberDialogComponent, {
      data: this.data,
      width: '520px',
      autoFocus: 'first-heading',
    });
  }
}
