import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

/**
 * Owned icon primitive (CDK + Tailwind stack — Material-free).
 *
 * Renders the material-icons FONT we already load (a `<span>` ligature), with
 * NO Angular Material `mat-icon`. Size and colour are controlled by the
 * consumer via Tailwind classes on the host, e.g.
 *
 *   <app-icon name="warning" class="text-[24px] text-warning-dark" />
 *
 * (font-size + colour inherit into the span, so the icon follows them).
 * Replaces `mat-icon` everywhere during the migration.
 */
@Component({
  selector: 'app-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="material-icons leading-none align-middle" aria-hidden="true">{{ name }}</span>`,
  styles: [`
    :host {
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
  `],
})
export class IconComponent {
  /** material-icons ligature name, e.g. "warning", "check_circle". */
  @Input({ required: true }) name = '';
}
