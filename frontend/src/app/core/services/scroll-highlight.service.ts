import { Injectable } from '@angular/core';
import { Subject, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import {
  calculateCenterScroll,
  validateAndGetElement,
} from '../utils/scroll-highlight.utils';

/**
 * Configuration options for scroll-and-highlight animation.
 */
export interface ScrollHighlightOptions {
  /** Scroll animation behavior: 'smooth' or 'auto'. Default: 'smooth' */
  scrollBehavior?: 'smooth' | 'auto';

  /** Duration to hold the highlight before fading (ms). Default: 6000 */
  highlightDuration?: number;

  /** Duration of the fade-out animation (ms). Default: 500 */
  fadeDuration?: number;

  /** CSS class to apply during highlight. Default: 'scroll-highlight' */
  highlightClass?: string;

  /** Duration of manual scroll animation (ms). Default: 350. Only used if scrollBehavior='auto' */
  scrollDuration?: number;

  /** Container to scroll (window or element). Default: window */
  scrollContainer?: HTMLElement | Window;

  /** Optional callback when animation completes */
  onComplete?: () => void;
}

/**
 * Service for smooth scroll-and-highlight navigation.
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
  private highlightCancellation$ = new Subject<void>();

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
    const targetElement = document.querySelector(selector.startsWith('#') ? selector : `#${selector}`) as HTMLElement;
    
    if (!targetElement) {
      return false;
    }

    try {
      // Validate and get the target element
      const targetElement = validateAndGetElement(selector);

      // Cancel any previous highlight
      this.cancelHighlight();

      // Set default options
      const {
        scrollBehavior = 'smooth',
        highlightDuration = 6000,
        fadeDuration = 500,
        highlightClass = 'scroll-highlight',
        scrollDuration = 350,
        scrollContainer = window,
        onComplete,
      } = options;

      // Store current element for cleanup
      this.currentHighlightElement = targetElement;

      // Perform smooth scroll to element
      this.performScroll(
        targetElement,
        scrollBehavior,
        scrollDuration,
        scrollContainer
      );

      // Apply highlight class
      targetElement.classList.add(highlightClass);

      // Schedule the highlight animation sequence
      this.scheduleHighlightSequence(
        targetElement,
        highlightClass,
        highlightDuration,
        fadeDuration,
        onComplete
      );

      return true;
    } catch (error) {
      // Log error but don't crash the app
      console.error('[ScrollHighlight]', error);
      return false;
    }
  }

  /**
   * Cancel the current highlight animation immediately.
   */
  cancelHighlight(): void {
    if (this.currentHighlightElement) {
      // Emit cancellation signal (cancels pending RxJS timers)
      this.highlightCancellation$.next();

      // Remove all highlight classes
      this.currentHighlightElement.classList.remove(
        'scroll-highlight',
        'scroll-highlight--fade'
      );

      // Reset state
      this.currentHighlightElement = null;
    }
  }

  /**
   * Perform the actual scroll animation.
   * Uses native scrollBehavior='smooth' or manual animation via requestAnimationFrame.
   */
  private performScroll(
    element: HTMLElement,
    behavior: 'smooth' | 'auto',
    duration: number,
    scrollContainer: HTMLElement | Window
  ): void {
    if (behavior === 'smooth') {
      // Use native smooth scroll
      if (scrollContainer instanceof Window) {
        window.scrollTo({ top: calculateCenterScroll(element), behavior: 'smooth' });
      } else {
        scrollContainer.scrollTo({ top: calculateCenterScroll(element, scrollContainer), behavior: 'smooth' });
      }
    } else {
      // Manual smooth scroll with requestAnimationFrame for custom duration
      this.animateScroll(
        calculateCenterScroll(element, scrollContainer),
        duration,
        scrollContainer
      );
    }
  }

  /**
   * Animate scroll over a specific duration using requestAnimationFrame.
   */
  private animateScroll(
    targetScroll: number,
    duration: number,
    scrollContainer: HTMLElement | Window
  ): void {
    const startScroll =
      scrollContainer instanceof Window
        ? window.scrollY || window.pageYOffset
        : scrollContainer.scrollTop;

    const startTime = performance.now();
    const distance = targetScroll - startScroll;

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease-out cubic for smooth deceleration
      const easeProgress = 1 - Math.pow(1 - progress, 3);
      const currentScroll = startScroll + distance * easeProgress;

      if (scrollContainer instanceof Window) {
        window.scrollTo(0, currentScroll);
      } else {
        scrollContainer.scrollTop = currentScroll;
      }

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  }

  /**
   * Schedule the highlight animation sequence (hold + fade).
   * Uses RxJS timer with switchMap to support cancellation.
   */
  private scheduleHighlightSequence(
    element: HTMLElement,
    highlightClass: string,
    highlightDuration: number,
    fadeDuration: number,
    onComplete?: () => void
  ): void {
    const fadeStartTime = highlightDuration - fadeDuration;

    this.highlightCancellation$
      .asObservable()
      .pipe(
        switchMap(() =>
          // Wait for highlight duration, then start fade
          timer(fadeStartTime).pipe(
            switchMap(() => {
              // Apply fade class to trigger CSS transition
              if (element === this.currentHighlightElement) {
                element.classList.add(`${highlightClass}--fade`);
              }

              // Wait for fade duration, then cleanup
              return timer(fadeDuration);
            })
          )
        )
      )
      .subscribe(() => {
        // Cleanup: remove all classes
        if (element === this.currentHighlightElement) {
          element.classList.remove(highlightClass, `${highlightClass}--fade`);
          this.currentHighlightElement = null;
        }

        // Call completion callback
        if (onComplete) {
          onComplete();
        }
      });

    // Start the timer sequence by emitting initial signal
    // This triggers switchMap chain above
    // We need to emit after a micro-task to allow subscription to be set up
    Promise.resolve().then(() => {
      this.highlightCancellation$.next();
    });
  }
}
