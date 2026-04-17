import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ExplainModeService } from '../../../core/services/explain-mode.service';

/**
 * Phase D1 / Gap 58 — Explain Mode info badge.
 *
 * Drop next to any metric or chart you want to annotate. When Explain
 * Mode is OFF the component renders nothing; when ON it shows a small
 * info icon whose tooltip contains the plain-English definition.
 *
 * Usage:
 *
 *   <h3>
 *     Suggestion funnel
 *     <app-explain-badge explanation="Counts of link suggestions by
 *       lifecycle stage: pending → approved → applied." />
 *   </h3>
 *
 * Sized to match an inline h-tag; doesn't disrupt existing layout.
 * Screen-reader text is always present via `aria-label` even when the
 * icon itself is hidden.
 */
@Component({
  selector: 'app-explain-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    @if (visible()) {
      <span
        class="eb"
        tabindex="0"
        role="button"
        [attr.aria-label]="'Explanation: ' + explanation"
        [matTooltip]="explanation"
        matTooltipPosition="above"
        matTooltipClass="eb-tooltip"
      >
        <mat-icon class="eb-icon" aria-hidden="true">info</mat-icon>
      </span>
    }
  `,
  styles: [`
    .eb {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-left: 4px;
      color: var(--color-text-secondary);
      cursor: help;
      vertical-align: middle;
    }
    .eb:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
      border-radius: 50%;
    }
    .eb:hover { color: var(--color-primary); }
    .eb-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
  `],
})
export class ExplainBadgeComponent {
  private readonly explain = inject(ExplainModeService);

  /** Plain-English definition displayed in the tooltip. */
  @Input({ required: true }) explanation = '';

  readonly visible = computed(() => this.explain.enabled() && !!this.explanation);
}
