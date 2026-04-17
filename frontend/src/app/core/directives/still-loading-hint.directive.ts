import {
  Directive,
  ElementRef,
  Input,
  OnChanges,
  OnDestroy,
  Renderer2,
  SimpleChanges,
  inject,
} from '@angular/core';

/**
 * Phase GK1 / Gap 200 — "Still loading…" reassurance hint.
 *
 * Pair with any loading spinner: after `delayMs` (default 3000) has
 * elapsed with `appStillLoading="true"`, the directive renders a
 * sibling `<span class="still-loading-hint">` next to the spinner
 * saying "Still loading… thanks for your patience."
 *
 * Usage:
 *   <mat-spinner diameter="24" [appStillLoading]="loading()" />
 */
@Directive({
  selector: '[appStillLoading]',
  standalone: true,
})
export class StillLoadingHintDirective implements OnChanges, OnDestroy {
  @Input('appStillLoading') loading: boolean = false;
  @Input() delayMs = 3000;
  @Input() hintText = 'Still loading… thanks for your patience.';

  private el = inject(ElementRef<HTMLElement>);
  private renderer = inject(Renderer2);

  private timer: ReturnType<typeof setTimeout> | null = null;
  private hintNode: HTMLElement | null = null;

  ngOnChanges(changes: SimpleChanges): void {
    if ('loading' in changes) {
      if (this.loading) this.start();
      else this.stop();
    }
  }

  ngOnDestroy(): void {
    this.stop();
  }

  private start(): void {
    this.clearTimer();
    this.removeHint();
    this.timer = setTimeout(() => this.renderHint(), this.delayMs);
  }

  private stop(): void {
    this.clearTimer();
    this.removeHint();
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private renderHint(): void {
    if (this.hintNode) return;
    const hint = this.renderer.createElement('span') as HTMLElement;
    this.renderer.addClass(hint, 'still-loading-hint');
    this.renderer.setAttribute(hint, 'role', 'status');
    this.renderer.setAttribute(hint, 'aria-live', 'polite');
    this.renderer.setStyle(hint, 'margin-left', '8px');
    this.renderer.setStyle(hint, 'font-size', '12px');
    this.renderer.setStyle(hint, 'color', 'var(--color-text-secondary, #5f6368)');
    hint.textContent = this.hintText;
    const parent = this.el.nativeElement.parentElement;
    if (parent) {
      this.renderer.appendChild(parent, hint);
      this.hintNode = hint;
    }
  }

  private removeHint(): void {
    if (!this.hintNode) return;
    this.hintNode.remove();
    this.hintNode = null;
  }
}
