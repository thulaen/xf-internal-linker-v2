import { ChangeDetectionStrategy, Component, Input, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Phase MX3 / Gap 349 — "Are we on track?" goal-progress meter.
 *
 * Drop on any dashboard card that owns a countable goal (weekly
 * approvals, monthly imports, etc.):
 *
 *   <app-goal-progress
 *     label="Approvals"
 *     [goal]="400"
 *     [progress]="276"
 *     [elapsedRatio]="5 / 7" />   <!-- 5 days into a 7-day week -->
 *
 * Colour tracks pace vs plan:
 *   • green  — progress ratio ≥ elapsed ratio (on or ahead)
 *   • amber  — 85% of elapsed ratio (behind but recoverable)
 *   • red    — < 85% (critical)
 */
@Component({
  selector: 'app-goal-progress',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatProgressBarModule, MatTooltipModule],
  template: `
    <div class="gp-card" [ngClass]="tone()">
      <header class="gp-head">
        <span class="gp-label">{{ label }}</span>
        <span class="gp-count">
          {{ progress.toLocaleString() }}
          /
          {{ goal.toLocaleString() }}
        </span>
      </header>
      <mat-progress-bar
        mode="determinate"
        [value]="progressPct()"
        [matTooltip]="paceTooltip()"
      />
      <p class="gp-pace" [matTooltip]="paceTooltip()">
        <mat-icon inline>{{ paceIcon() }}</mat-icon>
        {{ paceLabel() }}
      </p>
    </div>
  `,
  styles: [`
    .gp-card {
      padding: 12px;
      border-radius: 6px;
      background: var(--color-bg-faint, #f8f9fa);
      border-left: 4px solid var(--color-text-secondary, #5f6368);
    }
    .gp-card.gp-good { border-left-color: var(--color-success, #1e8e3e); }
    .gp-card.gp-warn { border-left-color: var(--color-warning, #f9ab00); }
    .gp-card.gp-bad  { border-left-color: var(--color-error, #d93025); }
    .gp-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 6px;
    }
    .gp-label {
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .gp-count {
      font-size: 12px;
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
    }
    .gp-pace {
      margin: 6px 0 0;
      font-size: 11px;
      color: var(--color-text-secondary);
      display: flex;
      align-items: center;
      gap: 4px;
    }
  `],
})
export class GoalProgressComponent {
  @Input({ required: true }) label!: string;
  @Input({ required: true }) goal!: number;
  @Input({ required: true }) progress!: number;
  /** 0..1. 0 = period just started, 1 = period is over. */
  @Input() elapsedRatio: number = 0.5;

  protected readonly progressPct = computed(() => {
    if (!this.goal || this.goal <= 0) return 0;
    const pct = (this.progress / this.goal) * 100;
    return Math.max(0, Math.min(100, pct));
  });

  tone(): string {
    const progressRatio = this.goal > 0 ? this.progress / this.goal : 0;
    if (progressRatio >= this.elapsedRatio) return 'gp-good';
    if (progressRatio >= this.elapsedRatio * 0.85) return 'gp-warn';
    return 'gp-bad';
  }

  paceIcon(): string {
    const t = this.tone();
    if (t === 'gp-good') return 'trending_up';
    if (t === 'gp-warn') return 'priority_high';
    return 'report';
  }

  paceLabel(): string {
    const t = this.tone();
    if (t === 'gp-good') return 'On track';
    if (t === 'gp-warn') return 'Slightly behind';
    return 'Significantly behind';
  }

  paceTooltip(): string {
    const expected = Math.round(this.goal * this.elapsedRatio);
    return `Expected by now: ${expected.toLocaleString()}. Actual: ${this.progress.toLocaleString()}.`;
  }
}
