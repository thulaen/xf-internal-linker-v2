import {
  ChangeDetectorRef,
  DestroyRef,
  Directive,
  ElementRef,
  HostListener,
  Input,
  OnDestroy,
  OnInit,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Phase E2 / Gap 50 — Character counter directive.
 *
 * Drop on any `<input>` or `<textarea>` that has a `maxlength` attribute:
 *
 *   <textarea matInput appCharCounter maxlength="500"></textarea>
 *
 * The directive injects a sibling `<span class="char-counter">` below the
 * field that shows `{current}/{max}`. Colors:
 *   - Default = `--color-text-secondary`.
 *   - At 80% = `--color-warning` (user should start wrapping up).
 *   - At 100% = `--color-error` (no more characters allowed).
 *
 * Works with `maxlength` from the DOM attribute OR the directive input
 * `[appCharCounter]="customLimit"` (the latter wins). This lets you show
 * a soft warning ("recommended under 160 chars for SMS") without actually
 * capping input.
 *
 * Accessibility:
 *   - The counter is `aria-live="polite"` so screen readers announce
 *     updates as the user types.
 *   - Linked to the field via `aria-describedby` so screen readers
 *     associate the count with the input they're editing.
 */
@Directive({
  selector: '[appCharCounter]',
  standalone: true,
})
export class CharCounterDirective implements OnInit, OnDestroy {
  /** Optional explicit max; falls back to the field's `maxlength` attr. */
  @Input('appCharCounter') limit: number | '' = '';

  private readonly host = inject<ElementRef<HTMLInputElement | HTMLTextAreaElement>>(ElementRef);
  private readonly renderer = inject(Renderer2);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);

  private counterEl: HTMLSpanElement | null = null;
  private resolvedLimit = 0;

  ngOnInit(): void {
    this.resolvedLimit = this.computeLimit();
    if (this.resolvedLimit <= 0) {
      // No limit anywhere — quietly no-op rather than misleading the user
      // with a meaningless "120/0" counter.
      return;
    }
    this.buildCounter();
    this.update();
  }

  ngOnDestroy(): void {
    if (this.counterEl?.parentNode) {
      this.counterEl.parentNode.removeChild(this.counterEl);
    }
    this.counterEl = null;
  }

  @HostListener('input')
  @HostListener('change')
  @HostListener('paste')
  onInput(): void {
    // setTimeout(0) so paste events see the pasted value, not the
    // pre-paste value.
    setTimeout(() => this.update(), 0);
  }

  // ── internals ──────────────────────────────────────────────────────

  private computeLimit(): number {
    const fromInput = typeof this.limit === 'number' ? this.limit : 0;
    if (fromInput > 0) return fromInput;
    const raw = this.host.nativeElement.getAttribute('maxlength');
    const asNum = raw ? Number.parseInt(raw, 10) : NaN;
    return Number.isFinite(asNum) && asNum > 0 ? asNum : 0;
  }

  private buildCounter(): void {
    const id = `char-counter-${Math.random().toString(36).slice(2, 8)}`;
    const span = this.renderer.createElement('span') as HTMLSpanElement;
    this.renderer.setAttribute(span, 'id', id);
    this.renderer.setAttribute(span, 'aria-live', 'polite');
    this.renderer.addClass(span, 'char-counter');

    // Wire aria-describedby so AT announces the counter when focus enters
    // the field.
    const existing = this.host.nativeElement.getAttribute('aria-describedby');
    this.renderer.setAttribute(
      this.host.nativeElement,
      'aria-describedby',
      existing ? `${existing} ${id}` : id,
    );

    // Insert immediately after the host. For mat-form-field wrappers the
    // consumer should place the counter via `<mat-hint align="end">`; for
    // plain inputs we inject a sibling.
    const parent = this.host.nativeElement.parentNode;
    parent?.insertBefore(span, this.host.nativeElement.nextSibling);
    this.counterEl = span;
  }

  private update(): void {
    if (!this.counterEl) return;
    const current = (this.host.nativeElement.value ?? '').length;
    const max = this.resolvedLimit;
    this.counterEl.textContent = `${current}/${max}`;

    // Color thresholds — 80% warning, 100% error.
    this.renderer.removeClass(this.counterEl, 'char-counter-warn');
    this.renderer.removeClass(this.counterEl, 'char-counter-over');
    if (current >= max) {
      this.renderer.addClass(this.counterEl, 'char-counter-over');
    } else if (current >= max * 0.8) {
      this.renderer.addClass(this.counterEl, 'char-counter-warn');
    }

    this.cdr.markForCheck();
  }
}
