import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D2 / Gap 66 — "Why am I seeing this?" footer strip.
 *
 * Drop inside the bottom of any card to give noobs a one-line answer
 * to "what is this card for?" — distinct from Tutorial Mode (Gap 55,
 * which renders ABOVE the card and is dismissable) and Explain Mode
 * (Gap 58, which annotates SPECIFIC METRICS inside the card body).
 *
 * Always visible, always small, never dismissable. The point is to be
 * the always-on safety net for "I forgot what this is for" — even
 * power users get the same footer; they just learn to ignore it.
 *
 * Usage:
 *   <mat-card>
 *     ...
 *     <app-why-footer
 *       text="Shows the top three things to do right now, ranked
 *             by urgency. Updates every 5 minutes." />
 *   </mat-card>
 */
@Component({
  selector: 'app-why-footer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule],
  template: `
    <footer class="wf">
      <mat-icon class="wf-icon" aria-hidden="true">help_outline</mat-icon>
      <span class="wf-label">Why am I seeing this?</span>
      <span class="wf-text">{{ text }}</span>
    </footer>
  `,
  styles: [`
    .wf {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      padding: 8px 12px;
      margin-top: auto;
      border-top: var(--card-border);
      background: var(--color-bg-faint);
      font-size: 11px;
      line-height: 1.5;
      color: var(--color-text-secondary);
      border-radius: 0 0 var(--card-border-radius, 8px) var(--card-border-radius, 8px);
    }
    .wf-icon {
      flex-shrink: 0;
      font-size: 14px;
      width: 14px;
      height: 14px;
      margin-top: 1px;
      color: var(--color-text-secondary);
    }
    .wf-label {
      font-weight: 500;
      color: var(--color-text-primary);
      white-space: nowrap;
    }
    .wf-text {
      flex: 1;
    }
  `],
})
export class WhyFooterComponent {
  /** Plain-English explanation of what the card is for and when to use it. */
  @Input({ required: true }) text = '';
}
