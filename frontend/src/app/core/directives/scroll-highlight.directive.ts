import { DestroyRef, Directive, EventEmitter, HostListener, Input, Output, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ScrollHighlightService, ScrollHighlightOptions } from '../services/scroll-highlight.service';

/**
 * Directive to attach scroll-and-highlight behavior to any clickable element.
 *
 * Works with:
 * - Buttons: <button appScrollHighlight="target-id">Go to Target</button>
 * - Links: <a appScrollHighlight="target-id">Go to Target</a>
 * - Menu items: <mat-menu-item appScrollHighlight="docs">Docs</mat-menu-item>
 * - Sidebar items: <a routerLink="/page" appScrollHighlight="section">Section</a>
 * - Any element: <div appScrollHighlight="id" role="button">Click</div>
 *
 * The directive automatically prevents default click behavior and triggers the scroll-highlight animation.
 * Supports optional configuration via scrollHighlightOptions input.
 *
 * Features:
 * - Works standalone or with routerLink for navigation + scroll/highlight
 * - Supports hash fragments: appScrollHighlight="#id" or appScrollHighlight="id"
 * - Optional configuration for custom timing and styles
 * - Event emission for completion callbacks
 * - Future-proof: Works with any element that can be clicked
 */
@Directive({
  selector: '[appScrollHighlight]',
  standalone: true,
})
export class ScrollHighlightDirective {
  private scrollHighlightService = inject(ScrollHighlightService);
  private routerLink = inject(RouterLink, { optional: true });
  private destroyRef = inject(DestroyRef);
  private pendingTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    this.destroyRef.onDestroy(() => {
      if (this.pendingTimeout !== null) {
        clearTimeout(this.pendingTimeout);
      }
      // Cancel any active scroll-highlight interval so the service's 200ms
      // setInterval does not keep polling the DOM after the host element is gone.
      this.scrollHighlightService.cancelHighlight();
    });
  }

  /**
   * The ID of the element to scroll to (with or without '#' prefix).
   * Required input for the directive to function.
   *
   * Examples:
   *   appScrollHighlight="section-1"
   *   appScrollHighlight="#section-1"
   *   appScrollHighlight="webhook-logs"
   */
  @Input() appScrollHighlight: string = '';

  /**
   * Optional configuration options for the scroll-and-highlight animation.
   * Can override default timing, colors (CSS class), callbacks, etc.
   */
  @Input() scrollHighlightOptions?: ScrollHighlightOptions;

  /**
   * Optional: delay before triggering scroll-and-highlight (ms).
   * Useful when combined with routerLink to wait for navigation to complete.
   * Default: 100ms (allows route to render)
   */
  @Input() scrollHighlightDelay: number = 100;

  /**
   * Event emitted when the scroll-and-highlight animation completes.
   * Useful for triggering side effects after highlighting finishes.
   */
  @Output() scrollComplete = new EventEmitter<void>();

  /**
   * Handle click events on the decorated element.
   * If used with routerLink, allows navigation to complete before scrolling.
   * Prevents default behavior and triggers scroll-and-highlight.
   */
  @HostListener('click', ['$event'])
  onClick(event: MouseEvent): void {
    // If using with routerLink, let router handle navigation first
    // RouterLink will handle the default behavior
    if (!this.routerLink && !this.appScrollHighlight.startsWith('#')) {
      event.preventDefault();
    }

    if (!this.appScrollHighlight) {
      console.warn('[ScrollHighlightDirective] appScrollHighlight input is required');
      return;
    }

    // Normalize selector (add # if not present)
    const selector = this.appScrollHighlight.startsWith('#')
      ? this.appScrollHighlight
      : `#${this.appScrollHighlight}`;

    // Create options with completion callback to emit event
    const optionsWithCallback: ScrollHighlightOptions = {
      ...this.scrollHighlightOptions,
      onComplete: () => {
        this.scrollComplete.emit();
        this.scrollHighlightOptions?.onComplete?.();
      },
    };

    // If routerLink is present, delay scroll-highlight to allow navigation to complete
    if (this.routerLink) {
      this.pendingTimeout = setTimeout(
        () => {
          this.pendingTimeout = null;
          this.scrollHighlightService.scrollToAndHighlight(selector, optionsWithCallback);
        },
        this.scrollHighlightDelay
      );
    } else {
      // Trigger scroll-and-highlight immediately
      this.scrollHighlightService.scrollToAndHighlight(selector, optionsWithCallback);
    }
  }
}
