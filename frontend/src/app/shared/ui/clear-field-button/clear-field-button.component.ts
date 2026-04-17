import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase FR / Gap 114 — Clear-field × button for inputs.
 *
 * Drop inside a `mat-form-field` as `matSuffix` to give an input a
 * one-click clear:
 *
 *   <mat-form-field>
 *     <input matInput [(ngModel)]="search" />
 *     <app-clear-field-button
 *       matSuffix
 *       [show]="!!search"
 *       (clear)="search = ''" />
 *   </mat-form-field>
 *
 * Renders nothing when `show` is false, so the suffix area collapses
 * naturally when the input is empty.
 */
@Component({
  selector: 'app-clear-field-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule],
  template: `
    @if (show) {
      <button
        mat-icon-button
        type="button"
        class="cfb"
        [attr.aria-label]="ariaLabel"
        (click)="onClear($event)"
      >
        <mat-icon>close</mat-icon>
      </button>
    }
  `,
  styles: [`
    .cfb {
      width: 28px;
      height: 28px;
      line-height: 28px;
    }
    .cfb mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: var(--color-text-secondary);
    }
    .cfb:hover mat-icon { color: var(--color-text-primary); }
  `],
})
export class ClearFieldButtonComponent {
  /** Render the button only when truthy. Bind to the field's value. */
  @Input() show = false;
  /** ARIA label. Default works for most cases. */
  @Input() ariaLabel = 'Clear field';
  @Output() clear = new EventEmitter<MouseEvent>();

  onClear(event: MouseEvent): void {
    event.stopPropagation();
    this.clear.emit(event);
  }
}
