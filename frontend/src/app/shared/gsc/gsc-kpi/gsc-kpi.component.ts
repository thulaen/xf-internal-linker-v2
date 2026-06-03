import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

type DeltaTone = 'positive' | 'negative' | 'flat';
type DeltaDirection = 'up' | 'down' | 'flat';

/**
 * GSC primitive — KPI cell.
 *
 * A label, a big number, and an optional change-since-last-period delta with a
 * direction arrow and colour (green good / red bad). Mirrors the metric cells
 * on the GSC Performance report and the "1.1K ↑+116%" style KPIs on the
 * SEMrush SEO dashboard.
 *
 * `lowerIsBetter` inverts the colour so a *fall* in something like "errors" or
 * "broken links" reads as good (green).
 *
 * Usage:
 *   <app-gsc-kpi label="Organic traffic" value="1.1K" [delta]="116" deltaSuffix="%" />
 *   <app-gsc-kpi label="Broken links" [value]="42" [delta]="-9" lowerIsBetter />
 *
 * Design rules: tokens only, no inline template styles, OnPush.
 */
@Component({
  selector: 'app-gsc-kpi',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="gsc-kpi">
      <span class="gsc-kpi__label">{{ label }}</span>
      <span class="gsc-kpi__value">{{ value }}</span>
      @if (delta !== null && delta !== undefined) {
        <span
          class="gsc-kpi__delta"
          [class.is-positive]="tone === 'positive'"
          [class.is-negative]="tone === 'negative'"
          [class.is-flat]="tone === 'flat'"
          [attr.aria-label]="deltaAriaLabel"
        >
          @if (direction !== 'flat') {
            <mat-icon aria-hidden="true">{{
              direction === 'up' ? 'arrow_upward' : 'arrow_downward'
            }}</mat-icon>
          }
          <span>{{ deltaText }}</span>
        </span>
      }
    </div>
  `,
  styles: [`
    .gsc-kpi {
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
      min-width: 0;
    }
    .gsc-kpi__label {
      font-size: var(--font-size-sm);
      color: var(--color-text-muted);
    }
    .gsc-kpi__value {
      font-size: 24px;
      font-weight: 500;
      color: var(--color-text-primary);
      line-height: 1.2;
    }
    .gsc-kpi__delta {
      display: inline-flex;
      align-items: center;
      gap: 2px;
      font-size: var(--font-size-sm);
      font-weight: 500;
    }
    .gsc-kpi__delta mat-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    .gsc-kpi__delta.is-positive { color: var(--color-success); }
    .gsc-kpi__delta.is-negative { color: var(--color-error); }
    .gsc-kpi__delta.is-flat { color: var(--color-text-muted); }
  `],
})
export class GscKpiComponent {
  /** Short metric label, e.g. "Organic traffic". */
  @Input({ required: true }) label = '';
  /** The headline value, pre-formatted (e.g. "1.1K") or a raw number. */
  @Input({ required: true }) value: string | number = '';
  /** Change since the previous period; null/undefined hides the delta. */
  @Input() delta: number | null | undefined = null;
  /** Unit appended to the delta (e.g. "%"). */
  @Input() deltaSuffix = '';
  /** When true, a fall is good (green) and a rise is bad (red). */
  @Input() lowerIsBetter = false;

  get direction(): DeltaDirection {
    const d = this.delta ?? 0;
    if (d > 0) return 'up';
    if (d < 0) return 'down';
    return 'flat';
  }

  get tone(): DeltaTone {
    if (this.direction === 'flat') return 'flat';
    const rising = this.direction === 'up';
    const good = this.lowerIsBetter ? !rising : rising;
    return good ? 'positive' : 'negative';
  }

  get deltaText(): string {
    const d = this.delta ?? 0;
    const sign = d > 0 ? '+' : '';
    return `${sign}${d}${this.deltaSuffix}`;
  }

  get deltaAriaLabel(): string {
    return $localize`:@@gsc.kpi.deltaAria:Change: ${this.deltaText}:delta:`;
  }
}
