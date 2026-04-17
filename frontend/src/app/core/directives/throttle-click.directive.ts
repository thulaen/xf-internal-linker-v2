import { Directive, HostListener, Input } from '@angular/core';

/**
 * Phase GK1 / Gap 206 — Client-side rate limit on destructive actions.
 *
 * Prevents double-click / rapid-fire on buttons that do something
 * destructive (delete, reset, trigger pipeline). Absorbs a click if it
 * arrives within `throttleMs` of the previous one; the button still
 * looks enabled so the user doesn't get "nothing happened" anxiety,
 * but the underlying (click) handler does not fire.
 *
 * Pair with Gap 208 idempotency keys for defence-in-depth: this
 * directive blocks accidental user input, the interceptor blocks
 * everything the directive missed.
 */
@Directive({
  selector: '[appThrottleClick]',
  standalone: true,
})
export class ThrottleClickDirective {
  @Input('appThrottleClick') throttleMs: number | string = 500;

  private lastFiredAt = 0;

  @HostListener('click', ['$event'])
  onClick(event: Event): void {
    const now = Date.now();
    const ms = typeof this.throttleMs === 'string' ? Number.parseInt(this.throttleMs, 10) : this.throttleMs;
    const window = Number.isFinite(ms) && ms > 0 ? ms : 500;
    if (now - this.lastFiredAt < window) {
      event.stopImmediatePropagation();
      event.preventDefault();
      return;
    }
    this.lastFiredAt = now;
  }
}
