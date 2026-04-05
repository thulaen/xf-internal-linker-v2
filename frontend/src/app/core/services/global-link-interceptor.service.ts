import { Injectable, OnDestroy, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Router, NavigationEnd } from '@angular/router';
import { Subject } from 'rxjs';
import { filter, takeUntil } from 'rxjs/operators';
import { ScrollHighlightService } from './scroll-highlight.service';
import { waitForElement, revealHiddenParent, waitForElementVisible } from '../utils/scroll-highlight.utils';

/**
 * Global link interceptor — registered once at app startup, works everywhere forever.
 *
 * Two things it does:
 *
 * 1. Document-level click listener (event delegation):
 *    Any <a href="#some-id"> anywhere in the app — present, past, or future —
 *    is automatically intercepted. Instead of the browser's instant jump, the
 *    page smoothly scrolls to that element and highlights it.
 *
 * 2. Router fragment listener:
 *    Any Angular Router navigation that ends with a fragment
 *    (e.g. routerLink="/page" fragment="section-id", or URL /page#section-id)
 *    automatically triggers scroll + highlight after the route renders.
 *    Uses MutationObserver to wait for lazy-loaded components instead of
 *    fragile setTimeout retries.
 *
 * Nothing needs to be added to individual components or templates.
 * Just give an element an id="..." and any link pointing to it works automatically.
 */
@Injectable({ providedIn: 'root' })
export class GlobalLinkInterceptorService implements OnDestroy {
  private router = inject(Router);
  private scrollHighlight = inject(ScrollHighlightService);
  private doc = inject(DOCUMENT);

  private destroy$ = new Subject<void>();
  private destroyed = false;
  // Bound reference stored so we can remove the exact same listener on destroy
  private boundClickHandler = this.onDocumentClick.bind(this);

  init(): void {
    // ── 1. Intercept all hash-anchor clicks in the document ──────────
    // useCapture=true so we see the event before any component handler,
    // but we skip it if preventDefault was already called (e.g. by the
    // explicit appScrollHighlight directive on the same element).
    this.doc.addEventListener('click', this.boundClickHandler, true);

    // ── 2. React to every router navigation that has a fragment ──────
    this.router.events.pipe(
      filter(e => e instanceof NavigationEnd),
      takeUntil(this.destroy$),
    ).subscribe((e: NavigationEnd) => {
      const fragment = this.router.parseUrl(e.urlAfterRedirects).fragment;
      if (!fragment) return;

      this.scrollToFragmentWhenReady(fragment);
    });
  }

  /**
   * Waits for an element to appear in the DOM (via MutationObserver),
   * reveals it if hidden inside a tab or accordion, confirms it is
   * visible, then scrolls and highlights.
   *
   * Handles lazy-loaded routes, tab panels, expansion panels, and
   * full page reloads — no setTimeout guessing.
   */
  private async scrollToFragmentWhenReady(fragment: string): Promise<void> {
    const element = await waitForElement(fragment, 5000);
    if (!element || this.destroyed) return;

    // If inside a hidden tab or collapsed panel, reveal it first
    await revealHiddenParent(element);
    if (this.destroyed) return;

    // Wait until the element is actually painted (handles animation delays)
    await waitForElementVisible(element, 2000);
    if (this.destroyed) return;

    this.scrollHighlight.scrollToAndHighlight(`#${fragment}`);
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.destroy$.next();
    this.destroy$.complete();
    this.doc.removeEventListener('click', this.boundClickHandler, true);
  }

  /**
   * Intercepts clicks anywhere in the document.
   * Walks up the DOM from the click target to find the nearest <a> tag.
   * If that anchor's href is a same-page hash link (#id), we take over:
   * prevent the browser's instant jump and run smooth scroll + highlight instead.
   */
  private onDocumentClick(event: MouseEvent): void {
    // If something else already called preventDefault (e.g. appScrollHighlight
    // directive) let that handler own the interaction.
    if (event.defaultPrevented) return;

    // Walk up the DOM tree from the click target to find an <a> element
    const anchor = (event.target as Element).closest('a');
    if (!anchor) return;

    const href = anchor.getAttribute('href');

    // Only handle same-page hash links: href="#some-id"
    if (!href || !href.startsWith('#')) return;

    const fragment = href.slice(1);
    if (!fragment) return;

    // Make sure the target element actually exists before we intervene
    const target = this.doc.getElementById(fragment);
    if (!target) return;

    event.preventDefault();
    this.scrollHighlight.scrollToAndHighlight(`#${fragment}`);
  }
}
