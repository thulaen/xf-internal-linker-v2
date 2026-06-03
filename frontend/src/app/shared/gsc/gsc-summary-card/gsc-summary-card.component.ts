import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { RouterModule } from '@angular/router';

/**
 * GSC primitive — Summary card.
 *
 * Mirrors the Google Search Console "Overview" card: a flat white card with a
 * title on the left, an optional "Full report ›" link on the right that routes
 * to the matching full page, and a projected body (mini chart, KPI row, etc.).
 *
 * This is the building block for the decluttered dashboard (Part 5): every
 * dashboard section becomes one of these, summarising an area and linking to
 * its full report — the calm GSC pattern that replaces the 67-widget wall.
 *
 * Usage:
 *   <app-gsc-summary-card title="Performance" reportLink="/analytics" icon="bar_chart">
 *     <app-gsc-kpi ... />
 *   </app-gsc-summary-card>
 *
 * Design rules: tokens only (no hardcoded hex), Angular Material card, all
 * styling in the component (no inline template styles), routed link via
 * routerLink so deep-linking + the back button work.
 */
@Component({
  selector: 'app-gsc-summary-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatCardModule, MatIconModule, RouterModule],
  template: `
    <mat-card class="gsc-summary-card">
      <div class="gsc-summary-card__head">
        @if (icon) {
          <mat-icon class="gsc-summary-card__icon" aria-hidden="true">{{ icon }}</mat-icon>
        }
        <h2 class="gsc-summary-card__title">{{ title }}</h2>
        @if (reportLink) {
          <a
            class="gsc-summary-card__report"
            [routerLink]="reportLink"
            [attr.aria-label]="reportAriaLabel"
          >
            <span>{{ reportLabel }}</span>
            <mat-icon aria-hidden="true">chevron_right</mat-icon>
          </a>
        }
      </div>
      <div class="gsc-summary-card__body">
        <ng-content />
      </div>
    </mat-card>
  `,
  styles: [`
    .gsc-summary-card {
      padding: var(--space-lg);                 /* 24px — content never touches the edge */
    }
    .gsc-summary-card__head {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin-bottom: var(--space-md);
    }
    .gsc-summary-card__icon {
      color: var(--color-primary);
      font-size: 20px;
      width: 20px;
      height: 20px;
      flex-shrink: 0;
    }
    .gsc-summary-card__title {
      flex: 1;
      margin: 0;
      font-size: var(--gsc-card-title-size);   /* 24px — measured from GSC */
      line-height: var(--gsc-card-title-lh);    /* 32px */
      font-weight: 400;                         /* GSC uses regular weight */
      color: var(--gsc-card-title-color);       /* #474747 soft charcoal */
      min-width: 0;
    }
    .gsc-summary-card__report {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      flex-shrink: 0;
      color: var(--color-primary);
      font-size: var(--font-size-lg);
      font-weight: 500;
      letter-spacing: 0.15px;                   /* GSC-measured link tracking */
      text-decoration: none;
    }
    .gsc-summary-card__report:hover {
      text-decoration: underline;
    }
    .gsc-summary-card__report:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
      border-radius: var(--radius-sm);
    }
    .gsc-summary-card__report mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }
  `],
})
export class GscSummaryCardComponent {
  /** Card heading, e.g. "Performance". */
  @Input({ required: true }) title = '';
  /** Route the "Full report" link points to; omit/null to hide the link. */
  @Input() reportLink: string | null = null;
  /** Link text. Defaults to the GSC wording. */
  @Input() reportLabel = $localize`:@@gsc.summaryCard.fullReport:Full report`;
  /** Optional Material icon shown before the title. */
  @Input() icon = '';

  get reportAriaLabel(): string {
    return $localize`:@@gsc.summaryCard.reportAria:${this.reportLabel}:label: for ${this.title}:title:`;
  }
}
