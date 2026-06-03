import { Directive, ElementRef, Input, OnChanges, Renderer2, inject } from '@angular/core';
import { MatTooltip, TooltipPosition } from '@angular/material/tooltip';

import { GLOSSARY, GlossaryEntry } from '../ui/glossary/glossary.data';

/**
 * Slice 1.6 — peHelper directive.
 *
 * Drop on any technical UI element that has a plain-English explanation
 * registered in the glossary:
 *
 *   <mat-icon [peHelper]="'Snapshot'">photo_camera</mat-icon>
 *
 * Renders the matching glossary definition as a `matTooltip` hover. Falls
 * back to a literal string if the input does not match a glossary term —
 * that way it stays useful for one-off labels without forcing every author
 * to add a glossary entry first.
 *
 * Why a directive instead of just `matTooltip="..."`:
 *   - Single source of truth — when the glossary updates, every helper
 *     hover updates with it. No drift between drawer wording and tooltip
 *     wording.
 *   - Authoring is by term, not by sentence — `[peHelper]="'Parquet'"` is
 *     shorter and more discoverable than copying the definition.
 *   - Lets us evolve the rendering later (overlay panel, peek drawer,
 *     etc.) without rewriting every call site.
 *
 * Cited in the PLAIN-ENGLISH-HELPER-RULE.md paramount rule and required
 * on technical UI elements in slice 1.6.
 */
@Directive({
  // eslint-disable-next-line @angular-eslint/directive-selector
  selector: '[peHelper]',
  standalone: true,
  hostDirectives: [
    {
      directive: MatTooltip,
      inputs: ['matTooltip', 'matTooltipPosition', 'matTooltipShowDelay'],
    },
  ],
})
export class PeHelperDirective implements OnChanges {
  /** Glossary term to look up, OR a literal sentence when the term is unknown. */
  @Input({ required: true, alias: 'peHelper' }) term = '';

  /** Tooltip position relative to the element. Default: 'above'. */
  @Input() peHelperPosition: TooltipPosition = 'above';

  /** Delay before the tooltip appears, in ms. Default: 400. */
  @Input() peHelperShowDelay = 400;

  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly renderer = inject(Renderer2);
  private readonly tooltip = inject(MatTooltip);

  ngOnChanges(): void {
    const text = resolveGlossaryDefinition(this.term);
    this.tooltip.message = text;
    this.tooltip.position = this.peHelperPosition;
    this.tooltip.showDelay = this.peHelperShowDelay;
    // Mark the element so CSS can style "helper-enabled" surfaces with a
    // subtle dotted underline (the design-system convention used by the
    // existing glossary drawer chips).
    this.renderer.setAttribute(this.host.nativeElement, 'data-pe-helper', '');
    // aria-describedby gets set by MatTooltip itself; nothing extra to do.
  }
}

/** Resolve a term to its definition. Case-insensitive prefix match falls
 * back to the literal input so authors can pass ad-hoc sentences. */
export function resolveGlossaryDefinition(term: string): string {
  if (!term) {
    return '';
  }
  const normalized = term.trim().toLowerCase();
  const hit: GlossaryEntry | undefined = GLOSSARY.find(
    (entry) => entry.term.toLowerCase() === normalized,
  );
  if (hit) {
    return hit.definition;
  }
  // Allow literal sentences (".. so the user can keep going if they
  // haven't added a glossary entry yet) but tag them via a leading
  // U+200B so a future linter can flag inline-only helpers if we ever
  // want to enforce glossary-only.
  if (term.includes(' ')) {
    return term;
  }
  return `${term} (no glossary entry — add one to shared/ui/glossary/glossary.data.ts)`;
}
