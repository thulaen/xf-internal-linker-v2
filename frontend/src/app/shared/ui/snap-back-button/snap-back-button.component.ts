import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Phase MX2 / Gap 314 — Safe-default snap-back per field.
 *
 * A tiny icon-button rendered next to any editable setting. Disabled
 * when the current value already matches the default, enabled the
 * moment the operator drifts from it. One click restores the default
 * and emits `(snap)` so the parent can persist.
 */
@Component({
  selector: 'app-snap-back-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <button
      mat-icon-button
      type="button"
      class="snap-btn"
      (click)="snap.emit(defaultValue)"
      [disabled]="matches"
      [matTooltip]="matches
        ? 'Already at the default'
        : 'Restore the default: ' + defaultValue"
      [attr.aria-label]="'Reset to default ' + defaultValue"
    >
      <mat-icon>restart_alt</mat-icon>
    </button>
  `,
  styles: [`
    .snap-btn {
      width: 28px;
      height: 28px;
      line-height: 28px;
    }
    .snap-btn mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }
  `],
})
export class SnapBackButtonComponent {
  @Input() current: string | number | null = null;
  @Input() defaultValue: string | number = '';
  @Output() snap = new EventEmitter<string | number>();

  get matches(): boolean {
    if (this.current === null || this.current === undefined) return false;
    return String(this.current).trim() === String(this.defaultValue).trim();
  }
}
