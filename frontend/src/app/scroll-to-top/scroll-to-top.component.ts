import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Input, NgZone, OnDestroy, OnInit, inject } from '@angular/core';
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
  private zone = inject(NgZone);
  // Store the bound reference so addEventListener and removeEventListener
  // receive the exact same function object.
  private readonly boundOnScroll = this.onScroll.bind(this);
  private rafPending = false;

  ngOnInit(): void {
    if (!this.scrollTarget) {
      this.scrollTarget = document.querySelector('.page-content');
    }
    // Listen outside Angular's zone so a fast scroll doesn't trigger global
    // change detection on every pixel. We re-enter the zone only when the
    // visibility flip actually changes via markForCheck().
    this.zone.runOutsideAngular(() => {
      this.scrollTarget?.addEventListener('scroll', this.boundOnScroll, { passive: true });
    });
  }

  ngOnDestroy(): void {
    this.scrollTarget?.removeEventListener('scroll', this.boundOnScroll);
  }

  private onScroll(): void {
    if (this.rafPending) return;
    this.rafPending = true;
    requestAnimationFrame(() => {
      this.rafPending = false;
      const wasVisible = this.visible;
      this.visible = (this.scrollTarget?.scrollTop ?? 0) > this.THRESHOLD;
      if (this.visible !== wasVisible) {
        // Re-enter Angular's zone so OnPush picks up the @if() flip.
        this.zone.run(() => this.cdRef.markForCheck());
      }
    });
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
