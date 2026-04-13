import { Directive, ElementRef, HostListener, inject } from '@angular/core';

@Directive({
  selector: '[appCardSpotlight]',
  standalone: true,
})
export class CardSpotlightDirective {
  private el = inject(ElementRef);

  @HostListener('mousemove', ['$event'])
  onMouseMove(event: MouseEvent): void {
    const rect = (this.el.nativeElement as HTMLElement).getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    (this.el.nativeElement as HTMLElement).style.setProperty('--mouse-x', `${x}px`);
    (this.el.nativeElement as HTMLElement).style.setProperty('--mouse-y', `${y}px`);
  }

  @HostListener('mouseleave')
  onMouseLeave(): void {
    (this.el.nativeElement as HTMLElement).style.removeProperty('--mouse-x');
    (this.el.nativeElement as HTMLElement).style.removeProperty('--mouse-y');
  }
}
