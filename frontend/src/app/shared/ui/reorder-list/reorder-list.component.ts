import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
  TemplateRef,
} from '@angular/core';
import { CommonModule, NgTemplateOutlet } from '@angular/common';
import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase FR / Gap 116 — Drag-reorder list field.
 *
 * Wrap an array of items + a per-item template to get drag-and-drop
 * reordering with keyboard support out of the box (cdk-drop-list
 * handles ArrowUp/ArrowDown when the drag handle is focused):
 *
 *   <app-reorder-list
 *     [items]="weights"
 *     [trackBy]="trackByKey"
 *     (reorder)="onReorder($event)"
 *   >
 *     <ng-template let-item>
 *       <span class="weight-name">{{ item.name }}</span>
 *       <span class="weight-value">{{ item.value | number }}</span>
 *     </ng-template>
 *   </app-reorder-list>
 *
 * Emits `(reorder)` with the new ordered array. Parent owns the
 * underlying list — the component is purely presentational.
 *
 * Keyboard:
 *   - Tab focuses the drag handle.
 *   - Space/Enter starts a drag-pickup mode (CDK default).
 *   - Arrow keys move the picked-up row.
 *   - Space/Enter drops; Escape cancels.
 */
@Component({
  selector: 'app-reorder-list',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, NgTemplateOutlet, DragDropModule, MatIconModule],
  template: `
    <ul
      cdkDropList
      class="rl"
      (cdkDropListDropped)="onDrop($event)"
      role="list"
    >
      @for (item of items; track trackBy($index, item)) {
        <li
          cdkDrag
          class="rl-item"
          role="listitem"
        >
          <button
            type="button"
            cdkDragHandle
            class="rl-handle"
            [attr.aria-label]="'Drag to reorder'"
          >
            <mat-icon>drag_indicator</mat-icon>
          </button>
          <div class="rl-body">
            <ng-container *ngTemplateOutlet="itemTemplate; context: { $implicit: item, index: $index }" />
          </div>
          <div class="rl-placeholder" *cdkDragPlaceholder></div>
        </li>
      }
    </ul>
  `,
  styles: [`
    .rl {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .rl-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: var(--color-bg-white);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      cursor: default;
    }
    .rl-handle {
      flex-shrink: 0;
      background: transparent;
      border: 0;
      cursor: grab;
      color: var(--color-text-secondary);
      padding: 4px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 4px;
    }
    .rl-handle:active { cursor: grabbing; }
    .rl-handle:hover { color: var(--color-primary); background: var(--color-bg-faint); }
    .rl-handle:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    .rl-body { flex: 1; min-width: 0; }
    .rl-placeholder {
      height: 36px;
      background: var(--color-bg-faint);
      border: 2px dashed var(--color-primary);
      border-radius: var(--card-border-radius, 8px);
    }
    .cdk-drag-preview {
      box-shadow: var(--shadow-md, 0 2px 6px rgba(60,64,67,.15));
    }
    .cdk-drag-placeholder { opacity: 0; }
    .cdk-drag-animating { transition: transform 0.15s cubic-bezier(0.4, 0, 0.2, 1); }
    @media (prefers-reduced-motion: reduce) {
      .cdk-drag-animating { transition: none; }
    }
  `],
})
export class ReorderListComponent<T = unknown> {
  /** Ordered items; parent owns the array. */
  @Input({ required: true }) items: readonly T[] = [];
  /** Required per-item template. Receives the item via $implicit and
   *  the index via let-i="index". */
  @Input({ required: true }) itemTemplate!: TemplateRef<{ $implicit: T; index: number }>;
  /** Stable identity for ngFor diffing. Default is the index. */
  @Input() trackBy: (index: number, item: T) => unknown = (i) => i;

  /** Emits the new ordered array after a successful reorder. */
  @Output() reorder = new EventEmitter<readonly T[]>();

  onDrop(event: CdkDragDrop<unknown>): void {
    if (event.previousIndex === event.currentIndex) return;
    const next = [...this.items];
    moveItemInArray(next, event.previousIndex, event.currentIndex);
    this.reorder.emit(next);
  }
}
