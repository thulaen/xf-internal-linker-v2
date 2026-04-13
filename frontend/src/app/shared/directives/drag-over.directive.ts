import { Directive, ElementRef, HostListener, inject } from '@angular/core';

@Directive({
  selector: '[appDragOver]',
  standalone: true,
})
export class DragOverDirective {
  private el = inject(ElementRef);

  @HostListener('dragover', ['$event'])
  onDragOver(event: DragEvent): void {
    event.preventDefault();
    (this.el.nativeElement as HTMLElement).classList.add('drag-over-active');
  }

  @HostListener('dragleave')
  onDragLeave(): void {
    (this.el.nativeElement as HTMLElement).classList.remove('drag-over-active');
  }

  @HostListener('drop')
  onDrop(): void {
    (this.el.nativeElement as HTMLElement).classList.remove('drag-over-active');
  }
}
