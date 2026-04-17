import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { baselineRangeLabel, significanceOf } from '../../util/statistics';

/**
 * Phase MX3 / Gaps 347 + 348 — Baseline indicator chip.
 *
 * Drop next to any numeric metric:
 *
 *   <app-baseline-indicator
 *     [current]="todayApprovals"
 *     [baseline]="last14DaysApprovals" />
 *
 * Shows:
 *   • the typical range pulled from baseline (μ ± σ)
 *   • a "↑ 2.3σ above baseline" marker when the current point is
 *     outside the 2σ band
 *   • green / amber / red tone depending on `goodDirection` —
 *     declaring that "up is good" flips the chip colour when the
 *     metric falls, and vice-versa.
 */
@Component({
  selector: 'app-baseline-indicator',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    <span
      class="bi-chip"
      [ngClass]="tone()"
      [matTooltip]="rangeLabel()"
      matTooltipPosition="above"
    >
      <mat-icon inline>{{ icon() }}</mat-icon>
      {{ verdict().marker }}
    </span>
  `,
  styles: [`
    .bi-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      font-variant-numeric: tabular-nums;
      background: var(--color-bg-faint, #f1f3f4);
      color: var(--color-text-secondary, #5f6368);
    }
    .bi-good    { background: #e6f4ea; color: #137333; }
    .bi-bad     { background: #fce8e6; color: #c5221f; }
    .bi-warn    { background: #fef7e0; color: #b06000; }
  `],
})
export class BaselineIndicatorComponent {
  @Input({ required: true }) current!: number;
  @Input({ required: true }) baseline: number[] = [];
  /** "up" means higher values are preferable (e.g. approvals, revenue);
   *  "down" means lower is preferable (errors, latency). */
  @Input() goodDirection: 'up' | 'down' = 'up';

  protected readonly verdict = computed(() => significanceOf(this.current, this.baseline));

  tone(): string {
    const v = this.verdict();
    if (v.direction === 'within') return '';
    const isGood =
      (this.goodDirection === 'up' && v.direction === 'above') ||
      (this.goodDirection === 'down' && v.direction === 'below');
    if (v.significant) return isGood ? 'bi-good' : 'bi-bad';
    return 'bi-warn';
  }

  icon(): string {
    return this.verdict().direction === 'above'
      ? 'north'
      : this.verdict().direction === 'below'
        ? 'south'
        : 'check_circle';
  }

  rangeLabel(): string {
    return baselineRangeLabel(this.baseline);
  }
}
