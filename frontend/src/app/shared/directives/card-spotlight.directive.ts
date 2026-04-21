import {
  AfterViewInit,
  DestroyRef,
  Directive,
  ElementRef,
  NgZone,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Tracks the cursor inside a card and exposes its position as CSS
 * custom properties (`--mouse-x`, `--mouse-y`) so the `.card` rule
 * can paint the spotlight gradient directly in CSS.
 *
 * The mousemove listener is attached OUTSIDE the Angular zone. A
 * `@HostListener('mousemove')` is registered through Angular's event
 * manager which always re-enters the zone — we cannot use it and must
 * use `Renderer2.listen` inside `runOutsideAngular`. Style writes do
 * not mutate Angular state, so no change detection is ever needed.
 * See docs/PERFORMANCE.md §13.
 */
@Directive({
  selector: '[appCardSpotlight]',
  standalone: true,
})
export class CardSpotlightDirective implements AfterViewInit {
  private readonly el = inject(ElementRef);
  private readonly renderer = inject(Renderer2);
  private readonly ngZone = inject(NgZone);
  private readonly destroyRef = inject(DestroyRef);

  ngAfterViewInit(): void {
    const host = this.el.nativeElement as HTMLElement;

    this.ngZone.runOutsideAngular(() => {
      const offMove = this.renderer.listen(host, 'mousemove', (event: MouseEvent) => {
        const rect = host.getBoundingClientRect();
        host.style.setProperty('--mouse-x', `${event.clientX - rect.left}px`);
        host.style.setProperty('--mouse-y', `${event.clientY - rect.top}px`);
      });
      const offLeave = this.renderer.listen(host, 'mouseleave', () => {
        host.style.removeProperty('--mouse-x');
        host.style.removeProperty('--mouse-y');
      });

      this.destroyRef.onDestroy(() => {
        offMove();
        offLeave();
      });
    });
  }
}
