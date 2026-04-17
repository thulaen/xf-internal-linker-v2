import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase U2 / Gap 9 — Shared "data-fetch failed" card.
 *
 * When a widget's data fetch errors out, the whole app used to either:
 *   - swallow the error and show a blank card, or
 *   - log to console and show nothing.
 *
 * This component is a drop-in replacement: render it INSIDE the failing
 * section with a plain-English heading, an optional message, and an
 * optional retry button. The consumer wires `(retry)` to its own
 * reload method.
 *
 * Usage:
 *   @if (loadError) {
 *     <app-error-card
 *       heading="Couldn't load metrics"
 *       [message]="loadError"
 *       (retry)="loadMetrics()" />
 *   }
 *
 * Severity tone optional (`error` / `warn` / `info`). Default `error`.
 * All colour comes from `var(--color-*)` tokens — no hex, no gradients.
 */
@Component({
  selector: 'app-error-card',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="error-card" [ngClass]="toneClass()" role="alert" aria-live="polite">
      <mat-icon class="error-card-icon" aria-hidden="true">{{ iconFor() }}</mat-icon>
      <div class="error-card-body">
        <h4 class="error-card-heading">{{ heading }}</h4>
        @if (message) {
          <p class="error-card-message">{{ message }}</p>
        }
      </div>
      @if (showRetry) {
        <button type="button"
                mat-stroked-button
                color="primary"
                class="error-card-retry"
                (click)="retry.emit()">
          <mat-icon>refresh</mat-icon>
          <span>{{ retryLabel }}</span>
        </button>
      }
    </div>
  `,
  styles: [`
    .error-card {
      display: flex;
      align-items: flex-start;
      gap: var(--space-sm, 8px);
      padding: var(--space-md, 16px);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-surface);
    }
    .error-card.tone-error {
      border-left: 4px solid var(--color-error);
      background: var(--color-error-light);
    }
    .error-card.tone-warn {
      border-left: 4px solid var(--color-warning);
      background: var(--color-warning-light);
    }
    .error-card.tone-info {
      border-left: 4px solid var(--color-primary);
      background: var(--color-blue-50);
    }
    .error-card-icon {
      flex: 0 0 auto;
    }
    .error-card.tone-error .error-card-icon {
      color: var(--color-error);
    }
    .error-card.tone-warn .error-card-icon {
      color: var(--color-warning-dark);
    }
    .error-card.tone-info .error-card-icon {
      color: var(--color-primary);
    }
    .error-card-body {
      flex: 1 1 auto;
    }
    .error-card-heading {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .error-card-message {
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .error-card-retry {
      flex: 0 0 auto;
      align-self: center;
    }
    .error-card-retry mat-icon {
      margin-right: 4px;
    }
  `],
})
export class ErrorCardComponent {
  /** Short plain-English title. Required. */
  @Input({ required: true }) heading!: string;

  /** Optional detail — a one-line explanation of what failed. */
  @Input() message?: string;

  /** Severity tone. `error` is red, `warn` is yellow, `info` is blue. */
  @Input() tone: 'error' | 'warn' | 'info' = 'error';

  /** Show / hide the retry button. Default shown. */
  @Input() showRetry = true;

  /** Button label. */
  @Input() retryLabel = 'Try again';

  /** Optional custom Material icon override. */
  @Input() icon?: string;

  /** Fires when the user clicks the retry button. */
  @Output() retry = new EventEmitter<void>();

  toneClass(): string {
    return `tone-${this.tone}`;
  }

  iconFor(): string {
    if (this.icon) return this.icon;
    switch (this.tone) {
      case 'warn': return 'warning';
      case 'info': return 'info';
      default:     return 'error_outline';
    }
  }
}
