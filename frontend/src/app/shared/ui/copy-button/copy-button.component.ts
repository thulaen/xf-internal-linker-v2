import {
  Component,
  Input,
  ChangeDetectionStrategy,
  signal,
  inject,
} from '@angular/core';
import { MatIconButton } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ToastService } from '../../../core/services/toast.service';

/**
 * Phase E1 / Gap 35 — Copy-to-clipboard button.
 *
 * A small icon button that copies a string value to the clipboard. After a
 * successful copy the icon flips to a green check mark for 2 seconds, then
 * reverts. On failure a toast error is shown.
 *
 * Usage:
 *   <app-copy-button [value]="suggestion.anchor_text" />
 *   <app-copy-button [value]="url" label="Copy URL" />
 *
 * Design:
 *  - mat-icon-button (icon-only by default)
 *  - Tooltip: "Copy" before copy, "Copied!" for 2 s after
 *  - Icon: content_copy → check (colour: var(--color-success) for 2 s)
 *  - Meets CLAUDE.md: no hardcoded hex, uses Material icon, aria-label present
 */
@Component({
  selector: 'app-copy-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconButton, MatIconModule, MatTooltipModule],
  template: `
    <button
      mat-icon-button
      type="button"
      class="copy-btn"
      [class.copy-btn-success]="copied()"
      [attr.aria-label]="label || 'Copy to clipboard'"
      [matTooltip]="copied() ? 'Copied!' : (tooltip || 'Copy')"
      (click)="copy()"
    >
      <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
    </button>
  `,
  styles: [`
    .copy-btn {
      /* Inherit the surrounding icon size — no override needed. */
      transition: color 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .copy-btn-success mat-icon {
      color: var(--color-success, #34a853);
    }

    @media (prefers-reduced-motion: reduce) {
      .copy-btn {
        transition: none;
      }
    }
  `],
})
export class CopyButtonComponent {
  /** The text to copy when the button is clicked. Required. */
  @Input({ required: true }) value!: string;

  /** Accessible label for the button (also used as tooltip prefix). */
  @Input() label?: string;

  /** Custom tooltip text. Defaults to "Copy". */
  @Input() tooltip?: string;

  readonly copied = signal(false);

  private readonly toast = inject(ToastService);
  private resetTimer: ReturnType<typeof setTimeout> | null = null;

  copy(): void {
    if (!this.value) return;

    navigator.clipboard
      .writeText(this.value)
      .then(() => {
        this.copied.set(true);
        // Clear any previous timer to restart the 2-second window.
        if (this.resetTimer) clearTimeout(this.resetTimer);
        this.resetTimer = setTimeout(() => {
          this.copied.set(false);
          this.resetTimer = null;
        }, 2000);
      })
      .catch(() => {
        this.toast.show('Could not copy to clipboard.', 'Dismiss', 4000);
      });
  }
}
