import { Injectable } from '@angular/core';
import { Subscription, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { validateAndGetElement } from '../utils/scroll-highlight.utils';

/**
 * Configuration options for scroll-and-highlight animation.
 */
export interface ScrollHighlightOptions {
  /** Scroll animation behavior: 'smooth' or 'auto'. Default: 'auto' */
  scrollBehavior?: 'smooth' | 'auto';

  /** Duration to hold the highlight before fading (ms). Default: 6000 */
  highlightDuration?: number;

  /** Duration of the fade-out animation (ms). Default: 500 */
  fadeDuration?: number;

  /** CSS class to apply during highlight. Default: 'scroll-highlight' */
  highlightClass?: string;

  /** Optional callback when animation completes */
  onComplete?: () => void;
}

/**
 * Service for scroll-and-highlight navigation.
 *
 * Provides a universal way to scroll to any element on the page and highlight it.
 * The element is centered in the viewport, highlighted with a subtle color, held
 * for 6 seconds, then faded out. Supports cancellation via RxJS for race condition prevention.
 *
 * Usage:
 *   inject(ScrollHighlightService).scrollToAndHighlight('#target-id');
 */
@Injectable({
  providedIn: 'root',
})
export class ScrollHighlightService {
  private currentHighlightElement: HTMLElement | null = null;
  private highlightSub: Subscription | null = null;

  // Tracks the selector so we can re-find the element after Angular re-renders it.
  // Angular's @if blocks destroy and recreate DOM elements on data change, so we
  // must use querySelector each tick rather than holding a stale DOM reference.
  private activeSelector: string | null = null;
  private activeHighlightClass: string | null = null;
  private reapplyInterval: ReturnType<typeof setInterval> | null = null;

  /**
   * Scroll to an element and apply highlight animation.
   *
   * @param selector CSS selector of target element (with or without '#')
   * @param options Configuration options
   */
  scrollToAndHighlight(
    selector: string,
    options: ScrollHighlightOptions = {}
  ): boolean {
    try {
      const targetElement = validateAndGetElement(selector);

      // Cancel any previous highlight
      this.cancelHighlight();

      const {
        scrollBehavior = 'auto',
        highlightDuration = 6000,
        fadeDuration = 500,
        highlightClass = 'scroll-highlight',
        onComplete,
      } = options;

      // Store the selector string so we can re-find the element if Angular
      // destroys and recreates it (e.g. inside an @if block on data change).
      const normalizedSelector = selector.startsWith('#') ? selector : `#${selector}`;
      this.activeSelector = normalizedSelector;
      this.activeHighlightClass = highlightClass;
      this.currentHighlightElement = targetElement;

      // Scroll element into center of viewport.
      // scrollIntoView handles any scroll container automatically (window, mat-sidenav-content, etc.)
      this.performScroll(targetElement, scrollBehavior);

      // Apply highlight class
      targetElement.classList.add(highlightClass);

      // Keep the class alive across Angular re-renders: poll every 200ms and
      // reapply to whichever DOM node currently matches the selector.
      this.startReapplyInterval(normalizedSelector, highlightClass);

      // Schedule the highlight animation sequence
      this.scheduleHighlightSequence(
        normalizedSelector,
        highlightClass,
        highlightDuration,
        fadeDuration,
        onComplete
      );

      return true;
    } catch (error) {
      console.error('[ScrollHighlight]', error);
      return false;
    }
  }

  /**
   * Cancel the current highlight animation immediately.
   */
  cancelHighlight(): void {
    this.stopReapplyInterval();

    this.highlightSub?.unsubscribe();
    this.highlightSub = null;

    const highlightClass = this.activeHighlightClass ?? 'scroll-highlight';
    const liveEl = this.activeSelector
      ? document.querySelector<HTMLElement>(this.activeSelector)
      : this.currentHighlightElement;

    liveEl?.classList.remove(highlightClass, `${highlightClass}--fade`);
    this.currentHighlightElement = null;
    this.activeSelector = null;
    this.activeHighlightClass = null;
  }

  /**
   * Scroll the element into the center of the viewport.
   * Uses scrollIntoView which handles any scroll container automatically —
   * works inside mat-sidenav-content, custom scroll panels, and window.
   */
  private performScroll(element: HTMLElement, behavior: 'smooth' | 'auto'): void {
    element.scrollIntoView({
      behavior: behavior === 'smooth' ? 'smooth' : 'instant',
      block: 'center',
    });
  }

  /**
   * Schedule the highlight animation sequence (hold + fade).
   * Uses RxJS timer with switchMap for cancellation.
   * Uses querySelector on each callback so that Angular @if re-renders
   * don't leave us with a stale element reference.
   */
  private scheduleHighlightSequence(
    selector: string,
    highlightClass: string,
    highlightDuration: number,
    fadeDuration: number,
    onComplete?: () => void
  ): void {
    const fadeStartTime = highlightDuration - fadeDuration;

    this.highlightSub?.unsubscribe();

    this.highlightSub = timer(fadeStartTime)
      .pipe(
        switchMap(() => {
          // Stop reapply interval — fade phase begins, class must not be re-added
          this.stopReapplyInterval();
          const liveEl = document.querySelector<HTMLElement>(selector);
          if (liveEl && selector === this.activeSelector) {
            liveEl.classList.add(`${highlightClass}--fade`);
          }
          return timer(fadeDuration);
        })
      )
      .subscribe(() => {
        const liveEl = document.querySelector<HTMLElement>(selector);
        if (liveEl) {
          liveEl.classList.remove(highlightClass, `${highlightClass}--fade`);
        }
        this.currentHighlightElement = null;
        this.activeSelector = null;
        this.activeHighlightClass = null;
        this.highlightSub = null;
        onComplete?.();
      });
  }

  /**
   * Poll every 200ms and reapply the highlight class if Angular has
   * destroyed and recreated the target element (e.g. inside an @if block).
   */
  private startReapplyInterval(selector: string, highlightClass: string): void {
    this.stopReapplyInterval();
    this.reapplyInterval = setInterval(() => {
      if (selector !== this.activeSelector) {
        this.stopReapplyInterval();
        return;
      }
      const liveEl = document.querySelector<HTMLElement>(selector);
      if (!liveEl) return;
      if (liveEl !== this.currentHighlightElement) {
        this.currentHighlightElement = liveEl;
      }
      if (!liveEl.classList.contains(highlightClass)) {
        liveEl.classList.add(highlightClass);
      }
    }, 200);
  }

  private stopReapplyInterval(): void {
    if (this.reapplyInterval !== null) {
      clearInterval(this.reapplyInterval);
      this.reapplyInterval = null;
    }
  }
}
