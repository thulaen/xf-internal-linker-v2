import { Directive, ElementRef, HostListener, inject } from '@angular/core';

@Directive({
  selector: '[appMagneticButton]',
  standalone: true,
})
export class MagneticButtonDirective {
  private el = inject(ElementRef);
  private strength = 0.3;

  @HostListener('mousemove', ['$event'])
  onMouseMove(event: MouseEvent): void {
    if (this.isReducedMotion() || this.isTouchDevice()) return;

    const el = this.el.nativeElement as HTMLElement;
    const rect = el.getBoundingClientRect();
    const x = (event.clientX - rect.left - rect.width / 2) * this.strength;
    const y = (event.clientY - rect.top - rect.height / 2) * this.strength;
    el.style.transform = `translate(${x}px, ${y}px)`;
  }

  @HostListener('mouseleave')
  onMouseLeave(): void {
    const el = this.el.nativeElement as HTMLElement;
    el.style.transform = '';
  }

  private isReducedMotion(): boolean {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  private isTouchDevice(): boolean {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  }
}
