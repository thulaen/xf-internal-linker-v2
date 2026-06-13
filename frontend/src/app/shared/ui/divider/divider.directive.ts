import { Directive, HostBinding, Input } from '@angular/core';

export type DividerOrientation = 'horizontal' | 'vertical';

/**
 * Owned divider primitive (Tailwind, Material-free) — replaces `mat-divider`.
 *
 * A 1px hairline rule in the border token colour (#dadce0). Apply to a native
 * separator element so semantics + a11y are preserved:
 *   <hr appDivider />
 *   <div appDivider orientation="vertical"></div>
 *
 * The divider carries no margin of its own — surrounding spacing comes from the
 * parent's gap (per the GSC spacing rules), so it never double-spaces.
 */
@Directive({
  selector: '[appDivider]',
  standalone: true,
})
export class DividerDirective {
  @Input() orientation: DividerOrientation = 'horizontal';

  @HostBinding('attr.role') readonly role = 'separator';

  @HostBinding('attr.aria-orientation')
  get ariaOrientation(): DividerOrientation {
    return this.orientation;
  }

  // A 1px line drawn as a thin token-coloured box, NOT a border: combining
  // `border-0` (to clear the <hr> UA border) with `border-t` collides — both
  // set border-top-width and `border-0` wins, leaving a 0px line. `bg-border`
  // on a 1px-thin element is unambiguous and preflight-independent.
  @HostBinding('class')
  get classes(): string {
    return this.orientation === 'vertical'
      ? 'inline-block self-stretch w-px border-0 bg-border mx-0'
      : 'block w-full h-px border-0 bg-border my-0';
  }
}
