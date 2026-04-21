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
 * Nudges the element toward the cursor while the pointer is inside it.
 *
 * The mousemove listener runs OUTSIDE the Angular zone — a
 * `@HostListener('mousemove')` re-enters the zone through Angular's
 * event manager and would fire full change detection ~100 times a
 * second. `Renderer2.listen` inside `runOutsideAngular` is the only
 * way to attach a native listener that stays out. Style writes do
 * not mutate Angular state so no change detection is ever needed.
 * See docs/PERFORMANCE.md §13.
 */
@Directive({
  selector: '[appMagneticButton]',
  standalone: true,
})
export class MagneticButtonDirective implements AfterViewInit {
  private readonly el = inject(ElementRef);
  private readonly renderer = inject(Renderer2);
  private readonly ngZone = inject(NgZone);
  private readonly destroyRef = inject(DestroyRef);
  private readonly strength = 0.3;

  ngAfterViewInit(): void {
    if (this.isReducedMotion() || this.isTouchDevice()) return;

    const host = this.el.nativeElement as HTMLElement;

    this.ngZone.runOutsideAngular(() => {
      const offMove = this.renderer.listen(host, 'mousemove', (event: MouseEvent) => {
        const rect = host.getBoundingClientRect();
        const x = (event.clientX - rect.left - rect.width / 2) * this.strength;
        const y = (event.clientY - rect.top - rect.height / 2) * this.strength;
        host.style.transform = `translate(${x}px, ${y}px)`;
      });
      const offLeave = this.renderer.listen(host, 'mouseleave', () => {
        host.style.transform = '';
      });

      this.destroyRef.onDestroy(() => {
        offMove();
        offLeave();
      });
    });
  }

  private isReducedMotion(): boolean {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  private isTouchDevice(): boolean {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  }
}
