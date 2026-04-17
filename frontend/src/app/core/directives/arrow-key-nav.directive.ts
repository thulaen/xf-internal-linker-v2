import {
  AfterViewInit,
  Directive,
  ElementRef,
  HostListener,
  Input,
  OnDestroy,
  inject,
} from '@angular/core';

/**
 * Phase GK2 / Gap 221 — Keyboard arrow-key navigation inside tables.
 *
 * Attach to a container holding a focusable list/table. Up/Down move
 * focus between rows that match `rowSelector` (default
 * `[role="row"], tr, li[role="option"]`). Enter clicks the focused
 * row.
 *
 * Rows get `tabindex="0"` on first mount so keyboard users can tab
 * into them; subsequent focus moves via programmatic focus() (no
 * tabindex cycling required).
 */
@Directive({
  selector: '[appArrowKeyNav]',
  standalone: true,
})
export class ArrowKeyNavDirective implements AfterViewInit, OnDestroy {
  @Input() rowSelector = '[role="row"], tr, li[role="option"], .row-navigable';

  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private observer: MutationObserver | null = null;

  ngAfterViewInit(): void {
    this.armRows();
    if (typeof MutationObserver !== 'undefined') {
      this.observer = new MutationObserver(() => this.armRows());
      this.observer.observe(this.host.nativeElement, {
        childList: true,
        subtree: true,
      });
    }
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
  }

  @HostListener('keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    if (ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp' && ev.key !== 'Enter') return;
    const rows = this.rows();
    if (!rows.length) return;
    const active = this.doc().activeElement as HTMLElement | null;
    const currentIdx = active ? rows.indexOf(active) : -1;

    if (ev.key === 'Enter') {
      if (currentIdx >= 0) {
        ev.preventDefault();
        active?.click();
      }
      return;
    }

    ev.preventDefault();
    const delta = ev.key === 'ArrowDown' ? 1 : -1;
    let nextIdx = currentIdx + delta;
    if (nextIdx < 0) nextIdx = 0;
    if (nextIdx >= rows.length) nextIdx = rows.length - 1;
    rows[nextIdx].focus();
  }

  private armRows(): void {
    for (const row of this.rows()) {
      if (!row.hasAttribute('tabindex')) row.setAttribute('tabindex', '0');
    }
  }

  private rows(): HTMLElement[] {
    return Array.from(
      this.host.nativeElement.querySelectorAll<HTMLElement>(this.rowSelector),
    ).filter((el) => !el.hasAttribute('disabled'));
  }

  private doc(): Document {
    return this.host.nativeElement.ownerDocument ?? document;
  }
}
