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

/**
 * Phase DC / Gap 121 — Bulk action toolbar.
 *
 * Appears above a data table when at least one row is selected.
 * Consumer provides the action buttons via `<ng-content>`, so the
 * toolbar can morph per page (suggestions support Approve/Reject,
 * alerts support Acknowledge, broken links support Ignore/Fix).
 *
 * Usage:
 *
 *   <app-bulk-action-toolbar
 *     [count]="selection.size()"
 *     (clearSelection)="selection.clear()"
 *   >
 *     <button mat-stroked-button (click)="approve(selection.ids())">
 *       Approve {{ selection.size() }} suggestions
 *     </button>
 *     <!-- more action buttons as <ng-content> -->
 *   </app-bulk-action-toolbar>
 *
 * Always sticky at the top of the scrollable table so the operator
 * can keep scrolling through rows while the count + actions stay in
 * view.
 */
@Component({
  selector: 'app-bulk-action-toolbar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    @if (count > 0) {
      <div class="bat" role="toolbar" aria-label="Bulk actions">
        <span class="bat-count">
          <strong>{{ count }}</strong>
          item{{ count === 1 ? '' : 's' }} selected
        </span>
        <span class="bat-actions">
          <ng-content />
        </span>
        <button
          mat-button
          type="button"
          class="bat-clear"
          aria-label="Clear selection"
          (click)="clearSelection.emit()"
        >
          <mat-icon>close</mat-icon>
          Clear
        </button>
      </div>
    }
  `,
  styles: [`
    .bat {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 16px;
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
      border-radius: var(--card-border-radius, 8px);
      box-shadow: var(--shadow-md);
      animation: bat-slide-in 0.15s ease;
    }
    .bat-count {
      font-size: 13px;
    }
    .bat-count strong {
      font-variant-numeric: tabular-nums;
    }
    .bat-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex: 1;
    }
    .bat-clear {
      color: var(--color-on-primary, #ffffff) !important;
    }
    .bat-clear mat-icon { margin-right: 4px; }
    @keyframes bat-slide-in {
      from { opacity: 0; transform: translateY(-4px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .bat { animation: none; }
    }
  `],
})
export class BulkActionToolbarComponent {
  /** Current selection count — pass `selection.size()` from BulkSelection. */
  @Input() count = 0;
  /** Emitted when the user clicks "Clear". Parent wires this to selection.clear(). */
  @Output() clearSelection = new EventEmitter<void>();
}
