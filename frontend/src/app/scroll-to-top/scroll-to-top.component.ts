import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-scroll-to-top',
  standalone: true,
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
    this.visible = (this.scrollTarget?.scrollTop ?? 0) > this.THRESHOLD;
  }

  scrollToTop(): void {
    this.scrollTarget?.scrollTo({ top: 0, behavior: 'smooth' });
  }
}
