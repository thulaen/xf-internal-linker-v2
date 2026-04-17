import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Skeleton screen — placeholder shown while a lazy-loaded route or widget
 * fetches its data. Phase U1 / Gap 2.
 *
 * Three shapes today:
 *   - `card`    — vertical stack of a header + three content lines
 *   - `table`   — N rows of five cells
 *   - `block`   — single rounded rectangle, sized by `height`
 *
 * Why a dedicated component rather than loose markup:
 *   - Consistent shimmer animation across every use (respects
 *     `prefers-reduced-motion` via `_attention.scss`-style media query).
 *   - One place to tune the colour / radius — currently uses
 *     `var(--color-border-faint)` for the bar and `var(--card-border)` for
 *     the outer frame, matching the GA4 card system.
 *   - OnPush change detection so skeletons never cause extra CD work.
 */
@Component({
  selector: 'app-skeleton',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (shape) {
      @case ('table') {
        <div class="skeleton-table" [attr.aria-busy]="true" role="status" aria-label="Loading content">
          @for (row of rowsArr; track row) {
            <div class="skeleton-row">
              <span class="skeleton-cell skeleton-cell-sm"></span>
              <span class="skeleton-cell skeleton-cell-md"></span>
              <span class="skeleton-cell skeleton-cell-lg"></span>
              <span class="skeleton-cell skeleton-cell-sm"></span>
              <span class="skeleton-cell skeleton-cell-sm"></span>
            </div>
          }
          <span class="visually-hidden">Loading…</span>
        </div>
      }
      @case ('block') {
        <div
          class="skeleton-block"
          [style.height.px]="height"
          [attr.aria-busy]="true"
          role="status"
          aria-label="Loading content">
          <span class="visually-hidden">Loading…</span>
        </div>
      }
      @default {
        <div class="skeleton-card" [attr.aria-busy]="true" role="status" aria-label="Loading content">
          <span class="skeleton-line skeleton-line-header"></span>
          <span class="skeleton-line skeleton-line-md"></span>
          <span class="skeleton-line skeleton-line-lg"></span>
          <span class="skeleton-line skeleton-line-sm"></span>
          <span class="visually-hidden">Loading…</span>
        </div>
      }
    }
  `,
  styleUrls: ['./skeleton.component.scss'],
})
export class SkeletonComponent {
  /** Layout shape. Default `card`. */
  @Input() shape: 'card' | 'table' | 'block' = 'card';

  /** For `table` shape: how many rows of placeholder to render. */
  @Input() rows = 4;

  /** For `block` shape: explicit height (px). */
  @Input() height = 120;

  /** trackBy — plain index so *ngFor never leaks identity. */
  get rowsArr(): number[] {
    return Array.from({ length: this.rows }, (_, i) => i);
  }
}
