import {
  Component,
  ChangeDetectionStrategy,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';

/**
 * Phase 0.15 — Friendly "this link needs setup first" dialog.
 *
 * When an operator clicks a deep link to a screen that requires an
 * unfilled prerequisite (e.g. a model dialog before any model is
 * configured, or a settings tab gated by a feature flag), routes
 * raise a CanActivate guard that opens THIS dialog instead of
 * falling through to a 404 or a blank page.
 *
 * The plain-English shape:
 *
 *   "This link points to <X>, but it needs <Y> first. Here's the
 *    quickest way to get there."
 *
 * Usage from a CanActivate guard:
 *
 *   const ok = await this.missingPrereq.show({
 *     targetLabel: 'Model details for DeBERTa',
 *     prereqLabel: 'a fine-tuned classifier model',
 *     instructions: [
 *       'Open Settings → Models',
 *       'Pick a base model and run "Fine-tune now"',
 *       'Come back to this link after training finishes',
 *     ],
 *     navigateTo: '/settings/models',
 *   });
 */
export interface MissingPrereqDialogData {
  /** Plain-English description of where the link points. */
  targetLabel: string;
  /** Plain-English description of what's missing. */
  prereqLabel: string;
  /** Step-by-step instructions to satisfy the prereq. */
  instructions: string[];
  /** Route to navigate to when the operator clicks "Take me there". */
  navigateTo?: string;
  /** Optional override for the primary CTA label. */
  ctaLabel?: string;
}

@Component({
  selector: 'app-missing-prereq-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <h2 mat-dialog-title class="prereq-title">
      <mat-icon class="prereq-title-icon" aria-hidden="true">info</mat-icon>
      Almost there
    </h2>

    <mat-dialog-content>
      <p class="prereq-summary">
        This link points to <strong>{{ data.targetLabel }}</strong>,
        but it needs <strong>{{ data.prereqLabel }}</strong> first.
      </p>
      @if (data.instructions.length > 0) {
        <p class="prereq-howto">Here's the quickest way to get there:</p>
        <ol class="prereq-steps">
          @for (step of data.instructions; track step) {
            <li>{{ step }}</li>
          }
        </ol>
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false">
        Stay on this page
      </button>
      @if (data.navigateTo) {
        <button
          mat-raised-button
          type="button"
          color="primary"
          class="prereq-action-btn"
          (click)="goToPrereq()"
        >
          {{ data.ctaLabel ?? 'Take me there' }}
        </button>
      }
    </mat-dialog-actions>
  `,
  styles: [`
    .prereq-title {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin: 0;
    }
    .prereq-title-icon {
      color: var(--color-primary);
    }
    .prereq-summary {
      margin: 0 0 var(--space-md);
      font-size: 14px;
      line-height: 1.5;
      color: var(--color-text-primary);
    }
    .prereq-howto {
      margin: 0 0 var(--space-sm);
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .prereq-steps {
      margin: 0;
      padding-left: var(--spacing-md);
      font-size: 14px;
      line-height: 1.6;
      color: var(--color-text-secondary);
    }
    .prereq-action-btn {
      margin-left: var(--space-sm);
    }
  `],
})
export class MissingPrereqDialogComponent {
  readonly data: MissingPrereqDialogData = inject(MAT_DIALOG_DATA);
  private readonly router = inject(Router);

  goToPrereq(): void {
    if (this.data.navigateTo) {
      this.router.navigateByUrl(this.data.navigateTo);
    }
  }
}
