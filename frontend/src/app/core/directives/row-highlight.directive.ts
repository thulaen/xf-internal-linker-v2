import {
  Directive,
  ElementRef,
  HostListener,
  Input,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Phase GK1 / Gap 218 — Highlight active / last-clicked row.
 *
 * Adds a `row-highlight-active` class to the host on click. The class
 * persists until another row with the same `appRowHighlight` group
 * key is clicked. Useful on tables where the user scrolls a long way
 * and wants to remember which row they just looked at.
 *
 * Coordinated via a tiny module-scope map keyed by group name — one
 * active row per group at any time.
 */

const _activeByGroup = new Map<string, HTMLElement>();

@Directive({
  selector: '[appRowHighlight]',
  standalone: true,
})
export class RowHighlightDirective {
  @Input('appRowHighlight') group = 'default';

  private el = inject(ElementRef<HTMLElement>);
  private renderer = inject(Renderer2);

  @HostListener('click')
  onClick(): void {
    const prev = _activeByGroup.get(this.group);
    if (prev && prev !== this.el.nativeElement) {
      this.renderer.removeClass(prev, 'row-highlight-active');
    }
    this.renderer.addClass(this.el.nativeElement, 'row-highlight-active');
    _activeByGroup.set(this.group, this.el.nativeElement);
  }
}
