import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

/**
 * Phase U2 / Gaps 6 + 8 — Shared loading-aware button.
 *
 * Every async action in the app needs the same thing: disable the
 * button while the request is in flight, show a Material spinner
 * beside the label, and re-enable on completion. Before this
 * component, that pattern was re-implemented in ~15 places with
 * subtle inconsistencies (spinner diameter varied, some buttons
 * forgot to disable on error, etc.).
 *
 * Usage:
 *   <app-loading-button
 *     [loading]="saving"
 *     (clicked)="onSave()">
 *     Save changes
 *   </app-loading-button>
 *
 * Material variants via `variant` input:
 *   - `primary`  → mat-flat-button + `color="primary"` (default)
 *   - `stroked`  → mat-stroked-button
 *   - `basic`    → mat-button
 *
 * The spinner sits INSIDE the button at 18 px — matches the
 * FRONTEND-RULES.md loading-state spec exactly. Button width is
 * preserved during loading by keeping the text visible.
 *
 * Accessibility:
 *   - `aria-busy="true"` while loading so screen readers announce
 *     "busy" without the user having to poll.
 *   - Native `disabled` covers keyboard / click / Enter / Space paths.
 */
@Component({
  selector: 'app-loading-button',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatProgressSpinnerModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (variant) {
      @case ('stroked') {
        <button type="button"
                mat-stroked-button
                [color]="color"
                [disabled]="loading || disabled"
                [attr.aria-busy]="loading"
                (click)="onClick($event)">
          <ng-container *ngTemplateOutlet="inner"></ng-container>
        </button>
      }
      @case ('basic') {
        <button type="button"
                mat-button
                [color]="color"
                [disabled]="loading || disabled"
                [attr.aria-busy]="loading"
                (click)="onClick($event)">
          <ng-container *ngTemplateOutlet="inner"></ng-container>
        </button>
      }
      @default {
        <button type="button"
                mat-flat-button
                [color]="color"
                [disabled]="loading || disabled"
                [attr.aria-busy]="loading"
                (click)="onClick($event)">
          <ng-container *ngTemplateOutlet="inner"></ng-container>
        </button>
      }
    }

    <ng-template #inner>
      @if (loading) {
        <mat-spinner class="btn-spinner"
                     [diameter]="18"
                     [attr.aria-label]="'Loading'"></mat-spinner>
      }
      <span class="btn-label" [class.btn-label-loading]="loading">
        <ng-content></ng-content>
      </span>
    </ng-template>
  `,
  styles: [`
    :host {
      display: inline-block;
    }
    .btn-spinner {
      display: inline-block;
      margin-right: 8px;
      vertical-align: middle;
    }
    .btn-label {
      display: inline-block;
      vertical-align: middle;
    }
    /* Keep the label at full opacity so the button doesn't jitter when
       the spinner appears/disappears — FRONTEND-RULES says "never let
       the user double-click and fire the action twice", we achieve
       that via disabled + aria-busy, not by hiding the label. */
    .btn-label-loading {
      opacity: 0.85;
    }
  `],
})
export class LoadingButtonComponent {
  /** True while the async action is in flight. Disables the button
   *  and renders the inline spinner. */
  @Input() loading = false;

  /** External disabled state (independent of loading). */
  @Input() disabled = false;

  /** Material colour. Applies to the chosen variant. */
  @Input() color: 'primary' | 'accent' | 'warn' | '' = 'primary';

  /** Visual variant — `primary` uses mat-flat-button, `stroked` uses
   *  mat-stroked-button, `basic` uses mat-button (no container). */
  @Input() variant: 'primary' | 'stroked' | 'basic' = 'primary';

  /** Fires on genuine clicks (swallowed while `loading` or `disabled`). */
  @Output() clicked = new EventEmitter<MouseEvent>();

  onClick(event: MouseEvent): void {
    if (this.loading || this.disabled) {
      event.stopPropagation();
      return;
    }
    this.clicked.emit(event);
  }
}
