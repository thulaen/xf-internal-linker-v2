import { Directive, HostBinding, Input } from '@angular/core';

export type CardPadding = 'default' | 'dense' | 'none';

/**
 * Owned card primitive (CDK + Tailwind stack — Material-free).
 *
 * A directive applied to a native container (`<div>`/`<section>`) that paints
 * the flat-white Google Search Console card surface: a 0.8px #dadce0 hairline
 * border, 12px radius, white fill, and NO resting shadow. Replaces `<mat-card>`.
 *
 *   <div appCard> ... </div>
 *   <section appCard padding="dense"> ... </section>
 *   <div appCard padding="none"> ...full-bleed header + own padding... </div>
 *
 * Colours/radius come from the token-mapped Tailwind theme (bg-surface,
 * border-border, rounded-card = 12px). Class strings are full literals so
 * Tailwind's scanner emits them. Tone/severity is NEVER a filled card
 * background — GSC cards are flat white; convey state with icon colour
 * (see GSC-DESIGN-SYSTEM.md).
 */
const BASE =
  'block bg-surface border-[0.8px] border-solid border-border rounded-card';

// Use the spacing TOKENS, not Tailwind's rem-based steps: this app sets the
// root font-size to 13px, so a rem-based `p-6` (1.5rem) resolves to 19.5px, not
// the GSC-measured 24px. Arbitrary token values pin the exact px.
const PADDING: Record<CardPadding, string> = {
  default: 'p-[var(--space-lg)]', // 24px — content never touches the card edge
  dense: 'p-[var(--space-md)]', //   16px — genuinely dense rows only
  none: '', //                       caller owns the inner padding
};

@Directive({
  selector: '[appCard]',
  standalone: true,
})
export class CardDirective {
  @Input() padding: CardPadding = 'default';

  @HostBinding('class')
  get classes(): string {
    return `${BASE} ${PADDING[this.padding]}`;
  }
}
