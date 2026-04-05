/**
 * Utility functions for scroll-and-highlight navigation system.
 * Pure functions for scroll calculations and element validation.
 */

/**
 * Calculate the scroll offset needed to center an element in the viewport.
 * Returns the scrollTop value that places the element in the vertical center.
 *
 * @param element The HTML element to center
 * @param scrollContainer The container to scroll (default: window)
 * @returns The scrollTop value for centering
 */
export function calculateCenterScroll(
  element: HTMLElement,
  scrollContainer: HTMLElement | Window = window
): number {
  const elementRect = element.getBoundingClientRect();
  const elementTop = elementRect.top;
  const elementHeight = element.offsetHeight;

  // Get viewport height
  const viewportHeight =
    scrollContainer instanceof Window
      ? window.innerHeight
      : scrollContainer.clientHeight;

  // Get current scroll position
  const currentScroll =
    scrollContainer instanceof Window
      ? window.scrollY || window.pageYOffset
      : scrollContainer.scrollTop;

  // Calculate scroll position to center element
  // Formula: currentScroll + elementTop - (viewportHeight / 2 - elementHeight / 2)
  const centeredScroll =
    currentScroll + elementTop - (viewportHeight / 2 - elementHeight / 2);

  return centeredScroll;
}

/**
 * Check if an element is visible within the viewport.
 * An element is considered visible if at least the specified threshold is in view.
 *
 * @param element The HTML element to check
 * @param threshold Minimum percentage visible to be considered visible (0-1, default: 0.5)
 * @returns true if element is visible, false otherwise
 */
export function isElementVisible(
  element: HTMLElement,
  threshold: number = 0.5
): boolean {
  const rect = element.getBoundingClientRect();
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth;

  // Check if element is below the viewport
  if (rect.bottom < 0 || rect.top > viewportHeight) {
    return false;
  }

  // Check if element is to the right or left of viewport
  if (rect.right < 0 || rect.left > viewportWidth) {
    return false;
  }

  // Calculate visible percentage
  const visibleTop = Math.max(0, rect.top);
  const visibleBottom = Math.min(viewportHeight, rect.bottom);
  const visibleHeight = Math.max(0, visibleBottom - visibleTop);
  const elementHeight = rect.height;

  const visiblePercentage =
    elementHeight > 0 ? visibleHeight / elementHeight : 0;

  return visiblePercentage >= threshold;
}

/**
 * Validate a selector and return the element, or throw an error.
 * Accepts selectors with or without '#' prefix.
 *
 * @param selector CSS selector (with or without '#')
 * @returns The HTMLElement if found
 * @throws Error if selector is invalid or element not found
 */
export function validateAndGetElement(selector: string): HTMLElement {
  if (!selector || typeof selector !== 'string') {
    throw new Error(
      `Invalid selector: "${selector}". Must be a non-empty string.`
    );
  }

  // Normalize selector (remove '#' if present)
  const normalizedSelector = selector.startsWith('#') ? selector : `#${selector}`;

  const element = document.querySelector<HTMLElement>(normalizedSelector);

  if (!element) {
    throw new Error(
      `Element not found for selector: "${normalizedSelector}". ` +
      `Make sure the element exists in the DOM and the ID matches.`
    );
  }

  return element;
}
