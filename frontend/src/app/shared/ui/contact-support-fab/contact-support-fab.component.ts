import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { FeatureRequestDialogComponent } from '../feature-request-dialog/feature-request-dialog.component';

/**
 * Phase GK2 / Gap 253 — Always-accessible Contact Support FAB.
 *
 * Bottom-left floating button. Opens the existing Gap 151 feature
 * request dialog — submissions land in the `FeatureRequest` inbox so
 * maintainers have one queue for both "feature asks" and "help me".
 *
 * Positioned bottom-left so it doesn't collide with the Gap 44
 * back-to-top FAB on the right. Respects `prefers-reduced-motion`
 * (hover lift is disabled when the media query matches).
 */
@Component({
  selector: 'app-contact-support-fab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatTooltipModule,
  ],
  template: `
    <button
      mat-fab
      class="csf-fab"
      color="primary"
      type="button"
      matTooltip="Contact support / suggest a feature"
      aria-label="Contact support"
      (click)="open()"
    >
      <mat-icon>help_outline</mat-icon>
    </button>
  `,
  styles: [`
    .csf-fab {
      position: fixed;
      left: 16px;
      bottom: 16px;
      z-index: 998;
      transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .csf-fab:hover {
      transform: translateY(-2px);
    }
    @media (prefers-reduced-motion: reduce) {
      .csf-fab:hover { transform: none; }
    }
  `],
})
export class ContactSupportFabComponent {
  private dialog = inject(MatDialog);

  open(): void {
    this.dialog.open(FeatureRequestDialogComponent, {
      width: '520px',
      restoreFocus: true,
    });
  }
}
