import {
  Directive,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnInit,
  Output,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Phase GK2 / Gap 248 — Pull-to-refresh on touch.
 *
 * Attach to a scrollable container. When the user touch-drags down
 * past `thresholdPx` (default 80) while scrollTop is 0, emits
 * `refresh`. Shows a small "Release to refresh ↻" indicator while
 * the gesture is in progress.
 *
 * Mouse/pen pointers are deliberately ignored — this is a mobile
 * affordance; desktop users have explicit refresh buttons.
 */
@Directive({
  selector: '[appPullToRefresh]',
  standalone: true,
})
export class PullToRefreshDirective implements OnInit {
  @Input() thresholdPx = 80;
  @Output() refresh = new EventEmitter<void>();

  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private renderer = inject(Renderer2);

  private startY = 0;
  private currentY = 0;
  private arming = false;
  private indicator: HTMLElement | null = null;

  ngOnInit(): void {
    const el = this.host.nativeElement;
    if (!el.style.touchAction) el.style.touchAction = 'pan-y';
  }

  @HostListener('pointerdown', ['$event'])
  onDown(ev: PointerEvent): void {
    if (ev.pointerType !== 'touch') return;
    const el = this.host.nativeElement;
    if (el.scrollTop !== 0) return;
    this.arming = true;
    this.startY = ev.clientY;
    this.currentY = ev.clientY;
  }

  @HostListener('pointermove', ['$event'])
  onMove(ev: PointerEvent): void {
    if (!this.arming) return;
    if (ev.pointerType !== 'touch') return;
    this.currentY = ev.clientY;
    const dy = this.currentY - this.startY;
    if (dy <= 0) {
      this.removeIndicator();
      return;
    }
    // Resist past the threshold so the gesture feels springy.
    const drag = Math.min(dy, this.thresholdPx * 1.5);
    this.showIndicator(drag >= this.thresholdPx, drag);
  }

  @HostListener('pointerup', ['$event'])
  @HostListener('pointercancel', ['$event'])
  onUp(ev: PointerEvent): void {
    if (!this.arming) return;
    if (ev && ev.pointerType && ev.pointerType !== 'touch') return;
    const dy = this.currentY - this.startY;
    this.arming = false;
    this.removeIndicator();
    if (dy >= this.thresholdPx) {
      this.refresh.emit();
    }
  }

  private showIndicator(armed: boolean, drag: number): void {
    if (!this.indicator) {
      const el = this.renderer.createElement('div') as HTMLElement;
      this.renderer.setAttribute(el, 'role', 'status');
      this.renderer.setAttribute(el, 'aria-live', 'polite');
      el.className = 'ptr-indicator';
      el.style.position = 'absolute';
      el.style.top = '8px';
      el.style.left = '50%';
      el.style.transform = 'translateX(-50%)';
      el.style.padding = '4px 12px';
      el.style.fontSize = '12px';
      el.style.color = 'var(--color-text-secondary, #5f6368)';
      el.style.background = 'var(--color-bg-faint, #f1f3f4)';
      el.style.borderRadius = '12px';
      el.style.zIndex = '99';
      el.style.pointerEvents = 'none';
      this.renderer.appendChild(this.host.nativeElement, el);
      this.indicator = el;
    }
    this.indicator.textContent = armed
      ? 'Release to refresh ↻'
      : 'Pull to refresh';
    this.indicator.style.opacity = String(Math.min(1, drag / this.thresholdPx));
  }

  private removeIndicator(): void {
    if (!this.indicator) return;
    this.indicator.remove();
    this.indicator = null;
  }
}
