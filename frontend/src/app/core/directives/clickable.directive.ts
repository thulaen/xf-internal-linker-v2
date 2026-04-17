import {
  Directive,
  ElementRef,
  HostBinding,
  HostListener,
  Input,
  OnInit,
  inject,
} from '@angular/core';

/**
 * Phase U2 / Gap 24 — Make any clickable element keyboard-accessible.
 *
 * Angular's FRONTEND-RULES require every interactive element be
 * reachable via Tab and activatable via Enter / Space. For native
 * `<button>` / `<a>` elements that's free; for custom `<div>` / `<li>`
 * / `<article>` handlers, it requires `role`, `tabindex`, and manual
 * keyboard event plumbing. This directive does all three in one line:
 *
 *   <article (click)="select(item)" appClickable>
 *     ...
 *   </article>
 *
 * The directive:
 *   - Adds `role="button"` if the host has no role.
 *   - Adds `tabindex="0"` if the host has no tabindex (so Tab reaches it).
 *   - Forwards `keydown.enter` and `keydown.space` to a synthetic click.
 *   - Preserves `(click)` — the host's existing handler still runs on
 *     both mouse and keyboard activation without the host component
 *     needing to care which triggered it.
 *
 * Opt-outs:
 *   - `[appClickable]="false"` disables the directive without
 *     removing it. Useful for routerLink anchors where Angular already
 *     handles keyboard activation.
 *   - Set `role="link"` explicitly on the host to override the default
 *     `role="button"`.
 */
@Directive({
  selector: '[appClickable]',
  standalone: true,
})
export class ClickableDirective implements OnInit {
  private readonly host = inject(ElementRef<HTMLElement>);

  /** Enable / disable. Default enabled. */
  @Input() appClickable: boolean | '' = true;

  ngOnInit(): void {
    if (this.appClickable === false) return;
    const el = this.host.nativeElement;
    // Respect pre-set role / tabindex so pages with custom ARIA
    // patterns aren't overridden.
    if (!el.hasAttribute('role')) el.setAttribute('role', 'button');
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
  }

  /** Space triggers the click — matches native button behaviour. */
  @HostListener('keydown.space', ['$event'])
  onSpace(event: KeyboardEvent): void {
    if (this.appClickable === false) return;
    // Prevent the default scroll-on-space behaviour inside lists.
    event.preventDefault();
    this.syntheticClick(event);
  }

  /** Enter triggers the click — matches native button + link behaviour. */
  @HostListener('keydown.enter', ['$event'])
  onEnter(event: KeyboardEvent): void {
    if (this.appClickable === false) return;
    event.preventDefault();
    this.syntheticClick(event);
  }

  @HostBinding('attr.data-appclickable')
  get marker(): string | null {
    return this.appClickable === false ? null : 'true';
  }

  /**
   * Fire a synthetic click so any `(click)` handler on the host runs
   * with the keyboard event as context. Using `.click()` rather than
   * `dispatchEvent` so Angular's zone picks it up for change detection.
   */
  private syntheticClick(source: KeyboardEvent): void {
    const el = this.host.nativeElement as HTMLElement & { click: () => void };
    if (typeof el.click === 'function') {
      el.click();
      // Explicitly stop propagation so ancestor keydown handlers don't
      // also fire — one keystroke, one action.
      source.stopPropagation();
    }
  }
}
