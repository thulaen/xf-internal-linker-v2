import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Input, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-scroll-to-top',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    @if (visible) {
      <button
        mat-fab
        class="scroll-btn"
        color="primary"
        matTooltip="Scroll to top"
        (click)="scrollToTop()"
        aria-label="Scroll to top"
      >
        <mat-icon>keyboard_arrow_up</mat-icon>
      </button>
    }
  `,
  styles: [`
    .scroll-btn {
      position: fixed;
      bottom: 32px;
      right: 32px;
      z-index: 1000;
      opacity: 0.9;
      transition: opacity 0.2s, transform 0.2s;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);

      &:hover { opacity: 1; transform: translateY(-2px); }
    }
  `],
})
export class ScrollToTopComponent implements OnInit, OnDestroy {
  @Input() scrollTarget: Element | null = null;

  visible = false;

  private readonly THRESHOLD = 300;
  private cdRef = inject(ChangeDetectorRef);
  // Store the bound reference so addEventListener and removeEventListener
  // receive the exact same function object.
  private readonly boundOnScroll = this.onScroll.bind(this);

  ngOnInit(): void {
    if (!this.scrollTarget) {
      this.scrollTarget = document.querySelector('.page-content');
    }
    this.scrollTarget?.addEventListener('scroll', this.boundOnScroll);
  }

  ngOnDestroy(): void {
    this.scrollTarget?.removeEventListener('scroll', this.boundOnScroll);
  }

  private onScroll(): void {
    const wasVisible = this.visible;
    this.visible = (this.scrollTarget?.scrollTop ?? 0) > this.THRESHOLD;
    // Gap 28 — with OnPush, DOM events outside Angular's zone don't trigger
    // change detection automatically. markForCheck() tells Angular to check
    // this component on the next cycle.
    if (this.visible !== wasVisible) {
      this.cdRef.markForCheck();
    }
  }

  scrollToTop(): void {
    // Phase E2 / Gap 44 + Gap 39 — respect the OS reduced-motion
    // preference. Smooth-scrolling a very long page is a known motion
    // trigger for vestibular disorders; we jump instead.
    const reduced =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.scrollTarget?.scrollTo({
      top: 0,
      behavior: reduced ? 'auto' : 'smooth',
    });
  }
}
