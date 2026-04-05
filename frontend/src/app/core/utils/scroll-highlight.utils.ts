/**
 * Utility functions for scroll-and-highlight navigation system.
 * Pure functions for scroll calculations and element validation.
 */

/**
 * Find the nearest scrollable ancestor of an element.
 * Walks up the DOM and returns the first ancestor with overflow auto/scroll
 * that actually has overflowing content (e.g. mat-sidenav-content).
 * Falls back to window if none is found.
 *
 * @param element The starting element
 * @returns The scrollable container element, or window as fallback
 */
export function getScrollableAncestor(element: HTMLElement): HTMLElement | Window {
  let parent = element.parentElement;
  while (parent && parent !== document.body) {
    const overflow = window.getComputedStyle(parent).overflowY;
    if ((overflow === 'auto' || overflow === 'scroll') && parent.scrollHeight > parent.clientHeight) {
      return parent;
    }
    parent = parent.parentElement;
  }
  return window;
}

/**
 * Calculate the scroll offset needed to center an element in the viewport.
 * Returns the scrollTop value that places the element in the vertical center.
 * Correctly accounts for the container's own top offset so centering is accurate
 * whether the container is window or a nested element like mat-sidenav-content.
 *
 * @param element The HTML element to center
 * @param scrollContainer The container to scroll (default: window)
 * @returns The scrollTop value for centering
 */
export function calculateCenterScroll(
  element: HTMLElement,
  scrollContainer: HTMLElement | Window = window
): number {
  const elementTop = element.getBoundingClientRect().top;
  const elementHeight = element.offsetHeight;

  // For non-window containers, getBoundingClientRect().top is viewport-relative,
  // so we must subtract the container's own top offset to get the element's
  // position relative to the container's visible area.
  const containerTop =
    scrollContainer instanceof Window
      ? 0
      : (scrollContainer as HTMLElement).getBoundingClientRect().top;

  const viewportHeight =
    scrollContainer instanceof Window
      ? window.innerHeight
      : (scrollContainer as HTMLElement).clientHeight;

  const currentScroll =
    scrollContainer instanceof Window
      ? window.scrollY || window.pageYOffset
      : (scrollContainer as HTMLElement).scrollTop;

  // Target: element top relative to container = center of container - half element height
  const centeredScroll =
    currentScroll + (elementTop - containerTop) - (viewportHeight / 2 - elementHeight / 2);

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
 * Wait for an element to appear in the DOM using MutationObserver.
 * Returns immediately if the element already exists (fast path).
 * Falls back to observing DOM mutations until the element appears or timeout.
 *
 * @param selector CSS selector (with or without '#')
 * @param maxWaitMs Maximum time to wait in milliseconds (default: 5000)
 * @returns The HTMLElement if found, or null on timeout
 */
export function waitForElement(
  selector: string,
  maxWaitMs: number = 5000
): Promise<HTMLElement | null> {
  const normalized = selector.startsWith('#') ? selector : `#${selector}`;

  // Fast path: element already exists
  const existing = document.querySelector<HTMLElement>(normalized);
  if (existing) {
    return Promise.resolve(existing);
  }

  return new Promise(resolve => {
    let resolved = false;

    const cleanup = (result: HTMLElement | null) => {
      if (resolved) return;
      resolved = true;
      observer.disconnect();
      clearTimeout(timeoutId);
      resolve(result);
    };

    const observer = new MutationObserver(() => {
      const el = document.querySelector<HTMLElement>(normalized);
      if (el) cleanup(el);
    });

    observer.observe(document.body, { childList: true, subtree: true });

    const timeoutId = setTimeout(() => cleanup(null), maxWaitMs);
  });
}

/**
 * Reveal a hidden parent container so the target element becomes visible.
 * Handles mat-tab-group (switches to the correct tab) and
 * mat-expansion-panel (expands the correct panel).
 *
 * @param element The target element that may be hidden inside a tab or accordion
 */
export async function revealHiddenParent(element: HTMLElement): Promise<void> {
  // ── Mat-Tab: switch to the tab containing the element ──────────
  const tabBody = element.closest('mat-tab-body');
  if (tabBody) {
    const tabGroup = tabBody.closest('mat-tab-group');
    if (tabGroup) {
      // Find the index of this tab body among its siblings
      const allBodies = Array.from(
        tabGroup.querySelectorAll(':scope > .mat-mdc-tab-body-wrapper > mat-tab-body')
      );
      const tabIndex = allBodies.indexOf(tabBody);

      if (tabIndex >= 0) {
        // Click the matching tab header if not already active
        const headers = tabGroup.querySelectorAll('.mat-mdc-tab');
        const targetHeader = headers[tabIndex] as HTMLElement | undefined;
        if (targetHeader && !targetHeader.classList.contains('mdc-tab--active')) {
          targetHeader.click();
          // Wait for Angular tab animation to complete
          await delay(300);
        }
      }
    }
  }

  // ── Mat-Expansion-Panel: expand the panel containing the element ──
  const panelBody = element.closest('.mat-expansion-panel-body');
  if (panelBody) {
    const panel = panelBody.closest('mat-expansion-panel');
    if (panel && !panel.classList.contains('mat-expanded')) {
      const header = panel.querySelector('mat-expansion-panel-header') as HTMLElement | null;
      if (header) {
        header.click();
        // Wait for Angular expansion animation to complete
        await delay(300);
      }
    }
  }
}

/**
 * Wait until an element is actually visible (painted with non-zero dimensions).
 * Uses IntersectionObserver for efficiency, with a fast path for already-visible elements.
 *
 * @param element The element to check
 * @param maxWaitMs Maximum time to wait (default: 2000)
 * @returns true if element became visible, false on timeout
 */
export function waitForElementVisible(
  element: HTMLElement,
  maxWaitMs: number = 2000
): Promise<boolean> {
  // Fast path: element already has dimensions (is painted)
  const rect = element.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) {
    return Promise.resolve(true);
  }

  return new Promise(resolve => {
    let resolved = false;

    const cleanup = (result: boolean) => {
      if (resolved) return;
      resolved = true;
      observer.disconnect();
      clearTimeout(timeoutId);
      resolve(result);
    };

    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(e => e.isIntersecting || e.intersectionRatio > 0)) {
          cleanup(true);
        }
      },
      { threshold: 0 }
    );

    observer.observe(element);

    const timeoutId = setTimeout(() => cleanup(false), maxWaitMs);
  });
}

/** Simple async delay helper */
function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
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
