import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { RouterModule } from '@angular/router';

type InsightTone = 'info' | 'warning' | 'success';

const DEFAULT_ICON: Record<InsightTone, string> = {
  info: 'tips_and_updates',
  warning: 'warning',
  success: 'check_circle',
};

/**
 * GSC primitive — Insight / "start here" banner.
 *
 * Mirrors the GSC Overview insight card and the SEMrush "start with these
 * issues" guidance card: a leading tone-coloured icon, a headline, an optional
 * detail line, and an optional action that routes to the fix.
 *
 * Becomes the top "attention banner" of the decluttered dashboard (Part 5):
 * surfaces the top thing that needs doing right now, with a one-click route to
 * fix it.
 *
 * Usage:
 *   <app-gsc-insight-card
 *     tone="warning"
 *     headline="Fix issues before running the pipeline"
 *     detail="System health is degraded"
 *     actionLabel="Fix" actionLink="/health" />
 *
 * Design rules: tokens only, Material card + stroked button, routed action,
 * no inline template styles, OnPush.
 */
@Component({
  selector: 'app-gsc-insight-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatCardModule, MatIconModule, MatButtonModule, RouterModule],
  template: `
    <mat-card
      class="gsc-insight"
      [class.tone-info]="tone === 'info'"
      [class.tone-warning]="tone === 'warning'"
      [class.tone-success]="tone === 'success'"
    >
      <div class="gsc-insight__row">
        <mat-icon class="gsc-insight__icon" aria-hidden="true">{{ resolvedIcon }}</mat-icon>
        <div class="gsc-insight__text">
          <span class="gsc-insight__headline">{{ headline }}</span>
          @if (detail) {
            <span class="gsc-insight__detail">{{ detail }}</span>
          }
        </div>
        @if (actionLink && actionLabel) {
          <a
            class="gsc-insight__action"
            mat-stroked-button
            [routerLink]="actionLink"
          >{{ actionLabel }}</a>
        }
      </div>
    </mat-card>
  `,
  styles: [`
    /* Spacing + rhythm ARE the design language. Generous card padding so
       content never touches the edge; a comfortable icon-to-text gap so the
       icon isn't jammed against the text; line-height + a row gap so the
       headline and detail breathe. Icon alignment is the global mat-icon rule
       (default-theme.scss); all values are tokens. Defined ONCE in this
       primitive, so every banner inherits the same calm rhythm. */
    .gsc-insight {
      padding: var(--space-lg);                /* 24px — room on every side */
    }
    .gsc-insight__row {
      display: flex;
      align-items: center;
      gap: var(--space-md);                    /* 16px — icon away from text */
    }
    .gsc-insight__icon {
      flex-shrink: 0;
      color: var(--color-text-muted);
    }
    .gsc-insight__text {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);                    /* 4px headline↔detail … */
      min-width: 0;
    }
    .gsc-insight__headline {
      font-size: var(--font-size-xl);          /* 16px — clear hierarchy */
      font-weight: 500;
      line-height: 1.45;                       /* … plus line-height to breathe */
      color: var(--color-text-primary);
    }
    .gsc-insight__detail {
      font-size: var(--font-size-sm);
      line-height: 1.45;
      color: var(--color-text-secondary);
    }
    .gsc-insight__action {
      flex-shrink: 0;
    }

    /* GSC insight cards are flat WHITE — tone is conveyed by the icon colour
       only, never a tinted background or coloured border (matches live GSC). */
    .gsc-insight.tone-info .gsc-insight__icon { color: var(--color-primary); }
    .gsc-insight.tone-warning .gsc-insight__icon { color: var(--color-warning-dark); }
    .gsc-insight.tone-success .gsc-insight__icon { color: var(--color-success-dark); }
  `],
})
export class GscInsightCardComponent {
  /** Visual tone — drives icon + colour. */
  @Input() tone: InsightTone = 'info';
  /** The main one-line message. */
  @Input({ required: true }) headline = '';
  /** Optional supporting line under the headline. */
  @Input() detail = '';
  /** Optional action button text. */
  @Input() actionLabel: string | null = null;
  /** Route the action button navigates to; both label + link required to show it. */
  @Input() actionLink: string | null = null;
  /** Optional Material icon override; defaults by tone. */
  @Input() icon = '';

  get resolvedIcon(): string {
    return this.icon || DEFAULT_ICON[this.tone];
  }
}
