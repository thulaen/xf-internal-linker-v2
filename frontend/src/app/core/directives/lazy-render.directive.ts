import {
  Directive,
  ElementRef,
  inject,
  OnDestroy,
  OnInit,
  TemplateRef,
  ViewContainerRef,
} from '@angular/core';

/**
 * Phase GK1 / Gap 204 — IntersectionObserver lazy render.
 *
 * Wraps a structural *ngIf-like template. The content mounts only when
 * the host element enters the viewport (or gets close to it via
 * `rootMargin: 200px`). On mount, the observer disconnects — there's
 * no point watching a rendered DOM node.
 *
 * Usage:
 *   <ng-template appLazyRender>
 *     <app-expensive-chart />
 *   </ng-template>
 *
 * Saves the render cost of deep charts/tables below the fold. Paired
 * with virtual scroll (Gap 27) for the worst offenders.
 */
@Directive({
  selector: '[appLazyRender]',
  standalone: true,
})
export class LazyRenderDirective implements OnInit, OnDestroy {
  private template = inject(TemplateRef<unknown>);
  private viewContainer = inject(ViewContainerRef);
  private hostEl = inject(ElementRef<HTMLElement>);

  private observer: IntersectionObserver | null = null;
  private mounted = false;

  ngOnInit(): void {
    if (typeof IntersectionObserver === 'undefined') {
      // No IO support → mount immediately. Better visible content than
      // locked-out content for old browsers.
      this.mount();
      return;
    }
    const sentinel = this.viewContainer.element.nativeElement as Node;
    const target = (sentinel && (sentinel as HTMLElement).nodeType === 1
      ? (sentinel as HTMLElement)
      : this.hostEl.nativeElement) as HTMLElement;

    this.observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            this.mount();
            this.disconnect();
            break;
          }
        }
      },
      { rootMargin: '200px' },
    );
    // IntersectionObserver needs an Element; ViewContainer anchors on a
    // comment node, so observe the parent element as a proxy.
    const parent = target.parentElement;
    if (parent) this.observer.observe(parent);
    else this.mount();
  }

  ngOnDestroy(): void {
    this.disconnect();
  }

  private mount(): void {
    if (this.mounted) return;
    this.mounted = true;
    this.viewContainer.createEmbeddedView(this.template);
  }

  private disconnect(): void {
    if (!this.observer) return;
    this.observer.disconnect();
    this.observer = null;
  }
}
