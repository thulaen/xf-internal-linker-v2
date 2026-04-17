import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { TutorialModeService } from '../../../core/services/tutorial-mode.service';

/**
 * Phase D1 / Gap 55 — Tutorial callout pill.
 *
 * Drop above or below any widget you want to annotate:
 *
 *   <app-tutorial-callout
 *     cardId="suggestion-funnel"
 *     title="Suggestion Funnel"
 *     body="Counts of suggestions by their lifecycle stage." />
 *
 * Renders nothing when tutorial mode is OFF or the user has dismissed
 * this particular callout. Otherwise shows a small info strip with a
 * "Got it" button that dismisses just this callout (doesn't affect
 * global tutorial mode).
 */
@Component({
  selector: 'app-tutorial-callout',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    @if (visible()) {
      <aside class="tc" role="note" aria-label="Tutorial hint">
        <mat-icon class="tc-icon" aria-hidden="true">school</mat-icon>
        <div class="tc-body">
          <span class="tc-title">{{ title }}</span>
          <span class="tc-text">{{ body }}</span>
        </div>
        <button
          mat-button
          class="tc-dismiss"
          type="button"
          (click)="onDismiss()"
        >
          Got it
        </button>
      </aside>
    }
  `,
  styles: [`
    .tc {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 8px 12px;
      margin-bottom: 8px;
      background: var(--color-blue-50, rgba(26, 115, 232, 0.08));
      border: var(--card-border);
      border-left: 3px solid var(--color-primary);
      border-radius: var(--card-border-radius, 8px);
    }
    .tc-icon {
      color: var(--color-primary);
      font-size: 18px;
      width: 18px;
      height: 18px;
      margin-top: 2px;
    }
    .tc-body {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .tc-title {
      font-weight: 500;
      font-size: 12px;
      color: var(--color-text-primary);
    }
    .tc-text {
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
    .tc-dismiss {
      flex-shrink: 0;
    }
  `],
})
export class TutorialCalloutComponent {
  private readonly tutorial = inject(TutorialModeService);

  /** Stable id used for dismissal — must be unique per callout. */
  @Input({ required: true }) cardId = '';
  /** Short noun-phrase headline. */
  @Input({ required: true }) title = '';
  /** One-sentence explanation. */
  @Input({ required: true }) body = '';

  /** Only render when tutorial mode is on AND this card isn't dismissed. */
  readonly visible = computed(() => {
    if (!this.cardId) return false;
    if (!this.tutorial.enabled()) return false;
    return !this.tutorial.isDismissed(this.cardId)();
  });

  onDismiss(): void {
    this.tutorial.dismiss(this.cardId);
  }
}
