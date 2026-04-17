import {
  Directive,
  ElementRef,
  HostBinding,
  HostListener,
  Input,
  inject,
} from '@angular/core';
import { MatTooltip } from '@angular/material/tooltip';

import { GLOSSARY } from '../ui/glossary/glossary.data';

/**
 * Phase D3 / Gap 178 — Hover-to-define jargon underline.
 *
 * Drop on any inline term you want to teach without breaking the flow:
 *
 *   The new <span [appJargon]="'embedding'">embedding</span> model
 *   produced 5% better recall.
 *
 * The directive looks the term up in the GLOSSARY bank and binds the
 * Material tooltip to the definition. Adds a subtle dotted underline
 * so users learn that underlined-dotted = hover for definition.
 *
 * If the term isn't in the bank, the directive renders no special UI
 * — it degrades to plain text.
 *
 * Standalone Angular directive; bring `MatTooltipModule` into the
 * consuming component for the tooltip to render.
 */
@Directive({
  selector: '[appJargon]',
  standalone: true,
  hostDirectives: [
    { directive: MatTooltip, inputs: ['matTooltipPosition'] },
  ],
})
export class JargonDirective {
  /** The lookup key — case-insensitive against GLOSSARY.term. */
  @Input({ alias: 'appJargon', required: true }) set term(value: string) {
    const def = this.lookup(value);
    this.matTooltip.message = def ?? '';
    this._known = !!def;
  }

  private _known = false;

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly matTooltip = inject(MatTooltip);

  @HostBinding('class.app-jargon')
  get appliedClass(): boolean {
    return this._known;
  }

  /** Make the underline keyboard-focusable so the tooltip is reachable
   *  for non-mouse users. Material tooltip already handles focus
   *  show/hide if the element is focusable. */
  @HostBinding('attr.tabindex')
  get tabindex(): string | null {
    return this._known ? '0' : null;
  }

  @HostBinding('attr.role')
  get role(): string | null {
    return this._known ? 'button' : null;
  }

  @HostListener('focus')
  onFocus(): void {
    if (this._known) this.matTooltip.show();
  }

  @HostListener('blur')
  onBlur(): void {
    this.matTooltip.hide();
  }

  // ── lookup ─────────────────────────────────────────────────────────

  private lookup(term: string): string | null {
    const norm = (term ?? '').trim().toLowerCase();
    if (!norm) return null;
    const hit = GLOSSARY.find((e) => e.term.toLowerCase() === norm);
    return hit ? hit.definition : null;
  }
}
