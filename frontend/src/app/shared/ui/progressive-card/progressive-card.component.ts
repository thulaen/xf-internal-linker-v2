import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnInit,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D1 / Gap 62 — Progressive Disclosure wrapper.
 *
 * A card that shows only a one-line headline by default and expands to
 * reveal its body on click. Lets a noob scan 10 cards in two seconds
 * and drill into whichever one interests them, rather than scrolling
 * through 10 expanded panels.
 *
 * Usage:
 *
 *   <app-progressive-card
 *     cardId="pipeline-runs"
 *     icon="play_arrow"
 *     title="Recent pipeline runs"
 *     headline="3 runs in the last 24h · last one took 12m"
 *   >
 *     <!-- Full detail content goes in the default slot -->
 *     <app-pipeline-runs-table [runs]="runs" />
 *   </app-progressive-card>
 *
 * Each card remembers its open/closed state per-user via localStorage
 * keyed by `cardId`. Callers can set `defaultOpen` to seed the initial
 * state for cards that should open by default on first visit.
 */

const EXPANDED_KEY_PREFIX = 'xfil_progressive_card_expanded.';

@Component({
  selector: 'app-progressive-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule],
  template: `
    <mat-card class="pc-card" [class.pc-expanded]="expanded()">
      <button
        type="button"
        class="pc-head"
        [attr.aria-expanded]="expanded()"
        [attr.aria-controls]="'pc-body-' + cardId"
        (click)="toggle()"
      >
        @if (icon) {
          <mat-icon class="pc-icon" aria-hidden="true">{{ icon }}</mat-icon>
        }
        <div class="pc-head-text">
          <span class="pc-title">{{ title }}</span>
          <span class="pc-headline">{{ headline }}</span>
        </div>
        <mat-icon class="pc-chevron" aria-hidden="true">
          {{ expanded() ? 'expand_less' : 'expand_more' }}
        </mat-icon>
      </button>
      <div
        class="pc-body"
        [id]="'pc-body-' + cardId"
        [hidden]="!expanded()"
      >
        <ng-content />
      </div>
    </mat-card>
  `,
  styles: [`
    .pc-card {
      transition: box-shadow 0.2s ease;
    }
    .pc-card.pc-expanded {
      box-shadow: var(--shadow-md);
    }
    .pc-head {
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;
      padding: 12px 16px;
      border: 0;
      background: transparent;
      cursor: pointer;
      text-align: left;
      color: var(--color-text-primary);
      font: inherit;
    }
    .pc-head:hover {
      background: var(--color-bg-faint);
    }
    .pc-head:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: -2px;
    }
    .pc-icon {
      color: var(--color-primary);
      font-size: 20px;
      width: 20px;
      height: 20px;
      flex-shrink: 0;
    }
    .pc-head-text {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .pc-title {
      font-weight: 500;
      font-size: 13px;
    }
    .pc-headline {
      font-size: 12px;
      color: var(--color-text-secondary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pc-chevron {
      color: var(--color-text-secondary);
      flex-shrink: 0;
    }
    .pc-body {
      padding: 0 16px 16px;
    }
    @media (prefers-reduced-motion: reduce) {
      .pc-card { transition: none; }
    }
  `],
})
export class ProgressiveCardComponent implements OnInit {
  /** Stable id used for persisting expanded state. Required. */
  @Input({ required: true }) cardId = '';
  /** Short noun-phrase title (e.g. "Recent pipeline runs"). */
  @Input({ required: true }) title = '';
  /** One-line summary shown while collapsed (e.g. "3 runs in 24h"). */
  @Input({ required: true }) headline = '';
  /** Optional Material icon name. */
  @Input() icon = '';
  /** Whether the card starts expanded on first visit. Default false. */
  @Input() defaultOpen = false;

  readonly expanded = signal(false);

  ngOnInit(): void {
    this.expanded.set(this.readExpanded());
  }

  toggle(): void {
    const next = !this.expanded();
    this.expanded.set(next);
    try {
      localStorage.setItem(EXPANDED_KEY_PREFIX + this.cardId, next ? '1' : '0');
    } catch {
      // In-memory only is fine.
    }
  }

  private readExpanded(): boolean {
    if (!this.cardId) return this.defaultOpen;
    try {
      const raw = localStorage.getItem(EXPANDED_KEY_PREFIX + this.cardId);
      if (raw === null) return this.defaultOpen;
      return raw === '1';
    } catch {
      return this.defaultOpen;
    }
  }
}
