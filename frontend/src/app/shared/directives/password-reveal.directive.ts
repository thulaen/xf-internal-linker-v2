import {
  Directive,
  ElementRef,
  HostListener,
  Input,
  OnInit,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Phase FR / Gap 115 — Show-password eye toggle directive.
 *
 * Drop on any `<input type="password">` to inject a small eye icon
 * inside the field's right padding that toggles between obscured
 * and visible:
 *
 *   <input
 *     matInput
 *     type="password"
 *     formControlName="password"
 *     appPasswordReveal
 *   />
 *
 * Uses an absolutely-positioned button so it works inside
 * mat-form-field without breaking the underline alignment.
 *
 * The directive flips the input's `type` between 'password' and 'text'
 * — no hidden DOM, no second copy of the value. Browser autofill keeps
 * working because the same node remains the form control.
 */
@Directive({
  selector: '[appPasswordReveal]',
  standalone: true,
})
export class PasswordRevealDirective implements OnInit {
  /** Optional override for the icon labels. */
  @Input() showLabel = 'Show password';
  @Input() hideLabel = 'Hide password';

  private readonly host = inject<ElementRef<HTMLInputElement>>(ElementRef);
  private readonly renderer = inject(Renderer2);

  private toggleBtn: HTMLButtonElement | null = null;
  private revealed = false;

  ngOnInit(): void {
    const input = this.host.nativeElement;
    if (input.tagName.toLowerCase() !== 'input') {
       
      console.warn('[appPasswordReveal] host is not an <input>');
      return;
    }

    this.toggleBtn = this.renderer.createElement('button') as HTMLButtonElement;
    this.renderer.setAttribute(this.toggleBtn, 'type', 'button');
    this.renderer.setAttribute(this.toggleBtn, 'aria-label', this.showLabel);
    this.renderer.addClass(this.toggleBtn, 'password-reveal-btn');

    // Use a Material icon ligature for visual consistency.
    const iconText = this.renderer.createText('visibility');
    const iconEl = this.renderer.createElement('span') as HTMLSpanElement;
    this.renderer.addClass(iconEl, 'material-icons');
    this.renderer.appendChild(iconEl, iconText);
    this.renderer.appendChild(this.toggleBtn, iconEl);

    this.renderer.listen(this.toggleBtn, 'click', (e: MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      this.toggle();
    });

    // Insert AFTER the input. Position is handled by the global
    // .password-reveal-btn rule in styles.scss.
    const parent = input.parentNode as HTMLElement | null;
    parent?.insertBefore(this.toggleBtn, input.nextSibling);
    if (parent) {
      // The mat-form-field wrapper needs relative positioning so the
      // button can absolutely position itself. mat-form-field already
      // does this in practice, but in plain forms we add it.
      const computed = window.getComputedStyle(parent);
      if (computed.position === 'static') {
        this.renderer.setStyle(parent, 'position', 'relative');
      }
    }
  }

  @HostListener('blur')
  onBlur(): void {
    // Re-mask on blur for safety so the password isn't left visible
    // when the user tabs away.
    if (this.revealed) this.toggle();
  }

  private toggle(): void {
    if (!this.toggleBtn) return;
    const input = this.host.nativeElement;
    this.revealed = !this.revealed;
    this.renderer.setAttribute(input, 'type', this.revealed ? 'text' : 'password');
    this.renderer.setAttribute(
      this.toggleBtn,
      'aria-label',
      this.revealed ? this.hideLabel : this.showLabel,
    );
    this.renderer.setAttribute(
      this.toggleBtn,
      'aria-pressed',
      String(this.revealed),
    );
    const iconEl = this.toggleBtn.querySelector('span');
    if (iconEl) {
      iconEl.textContent = this.revealed ? 'visibility_off' : 'visibility';
    }
  }
}
