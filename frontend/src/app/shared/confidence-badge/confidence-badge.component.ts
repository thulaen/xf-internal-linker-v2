import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-confidence-badge',
  standalone: true,
  imports: [MatChipsModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-chip
      [class]="'confidence-chip confidence-' + level"
      [matTooltip]="tooltip"
      disableRipple
    >
      {{ displayLabel }}
    </mat-chip>
  `,
  styles: [`
    .confidence-chip {
      font-size: 11px;
      height: 24px;
      font-weight: 500;
    }
    .confidence-high {
      --mdc-chip-elevated-container-color: var(--color-success-light);
      --mdc-chip-label-text-color: var(--color-success-dark);
    }
    .confidence-medium {
      --mdc-chip-elevated-container-color: var(--color-blue-50);
      --mdc-chip-label-text-color: var(--color-primary);
    }
    .confidence-low {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .confidence-thin {
      --mdc-chip-elevated-container-color: var(--color-bg-faint);
      --mdc-chip-label-text-color: var(--color-text-muted);
    }
  `],
})
export class ConfidenceBadgeComponent {
  @Input({ required: true }) level!: 'high' | 'medium' | 'low' | 'thin';
  @Input() label?: string;

  get displayLabel(): string {
    return this.label ?? this.defaultLabel;
  }

  private get defaultLabel(): string {
    switch (this.level) {
      case 'high': return 'High confidence';
      case 'medium': return 'Medium confidence';
      case 'low': return 'Low confidence';
      case 'thin': return 'Insufficient data';
    }
  }

  get tooltip(): string {
    switch (this.level) {
      case 'high': return 'Strong statistical evidence supports this result';
      case 'medium': return 'Moderate evidence — more data would strengthen this';
      case 'low': return 'Weak evidence — treat this as directional, not conclusive';
      case 'thin': return 'Not enough data to draw a meaningful conclusion';
    }
  }
}
