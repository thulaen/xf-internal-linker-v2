import {
  DestroyRef,
  Directive,
  ElementRef,
  Input,
  OnInit,
  Renderer2,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NgControl } from '@angular/forms';

/**
 * Phase FR / Gap 113 — Inline "valid" green checkmark on a control.
 *
 * Drop on a `<input matInput>` (or any NgControl host) to render a
 * small green ✓ inside the field's right padding once the value is
 * valid AND the user has touched the field. Lets the user know
 * they're done with that field without having to read mat-error.
 *
 *   <mat-form-field>
 *     <mat-label>Email</mat-label>
 *     <input matInput formControlName="email" appValidCheckmark />
 *   </mat-form-field>
 *
 * The checkmark is injected as a sibling `<span>` so it doesn't
 * disturb mat-form-field layout. Hidden when the control is invalid,
 * pristine, untouched, or disabled.
 *
 * Implementation note: we use Renderer2 + a <span> rather than a
 * structural directive because mat-form-field's layout is sensitive
 * to host-element attributes and a structural directive would force
 * the consumer to wrap the input in additional markup.
 */
@Directive({
  selector: '[appValidCheckmark]',
  standalone: true,
})
export class ValidCheckmarkDirective implements OnInit {
  /** Override the icon. Default Unicode check. */
  @Input() icon = '✓';

  private readonly control = inject(NgControl, { optional: true, self: true });
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly renderer = inject(Renderer2);
  private readonly destroyRef = inject(DestroyRef);

  private mark: HTMLSpanElement | null = null;

  ngOnInit(): void {
    const ctrl = this.control?.control;
    if (!ctrl) return;

    this.mark = this.renderer.createElement('span') as HTMLSpanElement;
    this.renderer.addClass(this.mark, 'valid-checkmark');
    this.renderer.setAttribute(this.mark, 'aria-hidden', 'true');
    this.renderer.appendChild(this.mark, this.renderer.createText(this.icon));

    // Insert immediately AFTER the host input. mat-form-field will
    // ignore unknown nodes inside its content and render normally.
    const parent = this.host.nativeElement.parentNode;
    parent?.insertBefore(this.mark, this.host.nativeElement.nextSibling);
    this.update(ctrl.valid, ctrl.touched, ctrl.disabled);

    ctrl.statusChanges
      ?.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.update(ctrl.valid, ctrl.touched, ctrl.disabled);
      });
  }

  private update(valid: boolean, touched: boolean, disabled: boolean): void {
    if (!this.mark) return;
    const visible = valid && touched && !disabled;
    this.renderer.setStyle(this.mark, 'display', visible ? 'inline-block' : 'none');
  }
}
