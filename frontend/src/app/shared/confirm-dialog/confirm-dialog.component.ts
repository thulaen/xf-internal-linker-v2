import {
  Component,
  ChangeDetectionStrategy,
  inject,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase E1 / Gap 30 — Reusable confirmation dialog.
 *
 * Usage (from any component):
 *
 *   import { ConfirmService } from 'app/shared/confirm-dialog/confirm.service';
 *
 *   constructor(private confirm: ConfirmService) {}
 *
 *   async onDelete() {
 *     const ok = await this.confirm.ask({
 *       title: 'Delete alert rule?',
 *       message: 'This cannot be undone.',
 *       confirmLabel: 'Delete',
 *       danger: true,
 *     });
 *     if (!ok) return;
 *     // … do the destructive thing
 *   }
 *
 * The dialog follows the Pattern spec from CLAUDE.md:
 *  - Title in <h2 mat-dialog-title>
 *  - Body in <mat-dialog-content>
 *  - Cancel left, confirm right in <mat-dialog-actions align="end">
 *  - Danger mode = warn (primary) button label
 */
export interface ConfirmDialogData {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** When true the confirm button renders in warn/red tone. */
  danger?: boolean;
  /** Optional Material icon next to the title. */
  icon?: string;
}

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <h2 mat-dialog-title class="confirm-title">
      @if (data.icon) {
        <mat-icon
          class="confirm-title-icon"
          [class.confirm-icon-danger]="data.danger"
          aria-hidden="true">{{ data.icon }}</mat-icon>
      }
      {{ data.title }}
    </h2>

    @if (data.message) {
      <mat-dialog-content>
        <p class="confirm-message">{{ data.message }}</p>
      </mat-dialog-content>
    }

    <mat-dialog-actions align="end">
      <button mat-button
              type="button"
              [mat-dialog-close]="false">
        {{ data.cancelLabel ?? 'Cancel' }}
      </button>
      <button mat-raised-button
              type="button"
              [color]="data.danger ? 'warn' : 'primary'"
              [mat-dialog-close]="true"
              class="confirm-action-btn">
        {{ data.confirmLabel ?? 'Confirm' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .confirm-title {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .confirm-title-icon {
      color: var(--color-text-secondary);
    }
    .confirm-icon-danger {
      color: var(--color-error);
    }
    .confirm-message {
      margin: 0;
      font-size: 14px;
      line-height: 1.5;
      color: var(--color-text-secondary);
    }
    .confirm-action-btn {
      margin-left: var(--space-sm);
    }
  `],
})
export class ConfirmDialogComponent {
  readonly data: ConfirmDialogData = inject(MAT_DIALOG_DATA) ?? { title: 'Confirm' };
}
