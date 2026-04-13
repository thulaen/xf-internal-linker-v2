import { Component, Input, inject, ChangeDetectionStrategy } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-explainability-tooltip',
  standalone: true,
  imports: [MatButtonModule, MatIconModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      mat-icon-button
      class="explain-btn"
      matTooltip="What does this mean?"
      aria-label="Explain this metric"
      (click)="open()"
    >
      <mat-icon class="explain-icon">info_outline</mat-icon>
    </button>
  `,
  styles: [`
    .explain-btn {
      width: 28px;
      height: 28px;
      line-height: 28px;
    }
    .explain-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: var(--color-text-muted);
    }
  `],
})
export class ExplainabilityTooltipComponent {
  @Input({ required: true }) what!: string;
  @Input({ required: true }) why!: string;
  @Input() whenBroken?: string;
  @Input() nextAction?: string;
  @Input() nextRoute?: string;

  private dialog = inject(MatDialog);

  open(): void {
    this.dialog.open(ExplainabilityDialogComponent, {
      width: '360px',
      data: {
        what: this.what,
        why: this.why,
        whenBroken: this.whenBroken,
        nextAction: this.nextAction,
        nextRoute: this.nextRoute,
      },
    });
  }
}

@Component({
  selector: 'app-explainability-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, MatIconModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>What does this mean?</h2>
    <mat-dialog-content>
      <section class="explain-section">
        <h4 class="explain-label">What it is</h4>
        <p class="explain-text">{{ data.what }}</p>
      </section>
      <section class="explain-section">
        <h4 class="explain-label">Why it matters</h4>
        <p class="explain-text">{{ data.why }}</p>
      </section>
      @if (data.whenBroken) {
        <section class="explain-section">
          <h4 class="explain-label">When something is wrong</h4>
          <p class="explain-text">{{ data.whenBroken }}</p>
        </section>
      }
      @if (data.nextAction) {
        <section class="explain-section">
          <h4 class="explain-label">What to do next</h4>
          <p class="explain-text">{{ data.nextAction }}</p>
        </section>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      @if (data.nextRoute) {
        <a mat-button [routerLink]="data.nextRoute" mat-dialog-close>
          Go there
        </a>
      }
      <button mat-button mat-dialog-close>Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .explain-section { margin-bottom: var(--space-md); }
    .explain-section:last-of-type { margin-bottom: 0; }
    .explain-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--color-text-muted);
      margin: 0 0 var(--space-xs);
    }
    .explain-text {
      font-size: 13px;
      color: var(--color-text-primary);
      margin: 0;
      line-height: 1.5;
    }
  `],
})
export class ExplainabilityDialogComponent {
  data = inject<{
    what: string;
    why: string;
    whenBroken?: string;
    nextAction?: string;
    nextRoute?: string;
  }>(MAT_DIALOG_DATA);
}

