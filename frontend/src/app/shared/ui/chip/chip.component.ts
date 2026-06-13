import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';

export type ChipTone = 'neutral' | 'primary';

/**
 * Owned chip primitive (Tailwind, Material-free) — replaces `mat-chip`.
 *
 * A compact pill for tags / filters / statuses. Flat tokened surface, pill
 * radius, no shadow. Tone is conveyed by a faint tinted fill (never a loud
 * colour). Optionally removable — shows a close affordance and emits
 * `(removed)`:
 *   <app-chip>Draft</app-chip>
 *   <app-chip tone="primary" [removable]="true" (removed)="drop()">Active</app-chip>
 */
const TONE: Record<ChipTone, string> = {
  neutral: 'bg-faint', //          inherits the dark body text
  primary: 'bg-blue-50 text-primary',
};

@Component({
  selector: 'app-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'inline-flex' },
  template: `
    <span [class]="classes">
      <ng-content></ng-content>
      @if (removable) {
        <button
          type="button"
          class="-mr-1 ml-1 inline-flex h-4 w-4 items-center justify-center rounded-pill text-current opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          [attr.aria-label]="removeLabel"
          (click)="removed.emit()"
        >
          <span class="material-icons text-[14px] leading-none">close</span>
        </button>
      }
    </span>
  `,
})
export class ChipComponent {
  @Input() tone: ChipTone = 'neutral';
  @Input() removable = false;
  @Input() removeLabel = 'Remove';
  @Output() removed = new EventEmitter<void>();

  get classes(): string {
    return `inline-flex items-center gap-1 rounded-pill px-3 h-7 text-xs font-medium ${TONE[this.tone]}`;
  }
}
