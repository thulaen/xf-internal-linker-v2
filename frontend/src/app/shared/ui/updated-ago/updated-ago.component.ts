import {
  Component,
  Input,
  OnChanges,
  OnDestroy,
  OnInit,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  inject,
} from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase E1 / Gap 37 — Staleness / "updated ago" pill.
 *
 * Shows how long ago data was last refreshed in human-readable form.
 * Turns yellow after `warnAfterMs` and red after `errorAfterMs` so users
 * can see at a glance when a widget's data is going stale.
 *
 * Ticks every `tickMs` to keep the label fresh without server round-trips.
 *
 * Usage:
 *   <app-updated-ago [updatedAt]="lastFetchedAt" />
 *   <app-updated-ago [updatedAt]="ts" [warnAfterMs]="300_000" />
 *
 * Design rules:
 *  - No hardcoded hex — uses `var(--color-*)` tokens.
 *  - Includes a matTooltip with the full ISO timestamp for accessibility.
 *  - Respects prefers-reduced-motion (icon transition removed).
 */
@Component({
  selector: 'app-updated-ago',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatTooltipModule, MatIconModule],
  template: `
    @if (updatedAt) {
      <span
        class="updated-ago-pill"
        [class.updated-ago-warn]="staleness === 'warn'"
        [class.updated-ago-error]="staleness === 'error'"
        [matTooltip]="tooltipText"
        matTooltipPosition="above"
        aria-label="Data last updated {{ label }}"
      >
        <mat-icon class="updated-ago-icon" aria-hidden="true">schedule</mat-icon>
        <span class="updated-ago-label">{{ label }}</span>
      </span>
    }
  `,
  styles: [`
    .updated-ago-pill {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      padding: 2px var(--space-sm);
      border-radius: 12px;
      border: var(--card-border);
      background: var(--color-bg-faint, #f8f9fa);
      font-size: 11px;
      color: var(--color-text-secondary);
      white-space: nowrap;
      transition: color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                  background 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .updated-ago-icon {
      font-size: 12px;
      width: 12px;
      height: 12px;
    }
    .updated-ago-warn {
      color: var(--color-warning-dark, #b45309);
      background: var(--color-warning-light, #fef9c3);
      border-color: var(--color-warning, #f59e0b);
    }
    .updated-ago-error {
      color: var(--color-error, #d93025);
      background: var(--color-error-light, #fde8e7);
      border-color: var(--color-error, #d93025);
    }

    @media (prefers-reduced-motion: reduce) {
      .updated-ago-pill {
        transition: none;
      }
    }
  `],
})
export class UpdatedAgoComponent implements OnInit, OnChanges, OnDestroy {
  /** ISO timestamp or Date when data was last successfully fetched. */
  @Input() updatedAt: string | Date | null | undefined;

  /** Show warning colour after this many ms of staleness. Default 5 min. */
  @Input() warnAfterMs = 5 * 60 * 1000;

  /** Show error colour after this many ms of staleness. Default 15 min. */
  @Input() errorAfterMs = 15 * 60 * 1000;

  /** How often to update the label. Default 30 s. */
  @Input() tickMs = 30_000;

  label = '';
  tooltipText = '';
  staleness: 'ok' | 'warn' | 'error' = 'ok';

  private timer: ReturnType<typeof setInterval> | null = null;
  private cdRef = inject(ChangeDetectorRef);

  ngOnInit(): void {
    this.recalculate();
    this.timer = setInterval(() => {
      this.recalculate();
      this.cdRef.markForCheck();
    }, this.tickMs);
  }

  ngOnChanges(): void {
    this.recalculate();
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  private recalculate(): void {
    if (!this.updatedAt) {
      this.label = '';
      this.staleness = 'ok';
      return;
    }

    const ts = typeof this.updatedAt === 'string'
      ? new Date(this.updatedAt)
      : this.updatedAt;

    const ageMs = Date.now() - ts.getTime();
    this.label = formatAgo(ageMs);
    this.tooltipText = `Last updated: ${ts.toLocaleString()}`;

    if (ageMs >= this.errorAfterMs) {
      this.staleness = 'error';
    } else if (ageMs >= this.warnAfterMs) {
      this.staleness = 'warn';
    } else {
      this.staleness = 'ok';
    }
  }
}

/** Format a duration in ms as a short human-readable string. */
function formatAgo(ms: number): string {
  if (ms < 0) return 'just now';
  const s = Math.floor(ms / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}
