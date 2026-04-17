import { Injectable, inject } from '@angular/core';
import { ScrollHighlightService } from './scroll-highlight.service';

/**
 * Priority level for an attention request. Maps to visual intensity and
 * whether focus is forcibly moved even if the user is typing elsewhere.
 */
export type AttentionPriority = 'low' | 'normal' | 'urgent';

/**
 * Configuration options for a scroll-attention request.
 */
export interface ScrollAttentionOptions {
  /**
   * Priority level. `urgent` pulses red and steals focus unconditionally;
   * `normal` pulses blue and moves focus only if the user is not typing;
   * `low` pulses subtly and never steals focus. Default: `'normal'`.
   */
  priority?: AttentionPriority;

  /**
   * CSS class applied for the pulse animation. Defaults map to priority:
   * - low     -> `attention-pulse-low`
   * - normal  -> `attention-pulse`
   * - urgent  -> `attention-pulse-urgent`
   */
  pulseClass?: string;

  /**
   * Optional plain-English announcement for screen readers.
   * If provided, emitted via an aria-live polite region.
   */
  announce?: string;

  /** Callback when the attention pulse has finished. */
  onComplete?: () => void;
}

/**
 * ScrollAttentionService — cross-cutting foundation for every phase that
 * needs to draw a user's attention to a specific widget (Mission Critical
 * red tile, new critical error row, form field with a validation error,
 * re-occurring alert, etc.).
 *
 * Phase GB / Gap 148 of the approved plan.
 *
 * Responsibilities (distinct from ScrollHighlightService which is
 * user-initiated "go to the thing I clicked"):
 *  - System-initiated attention-drawing
 *  - Priority levels (low / normal / urgent) with distinct pulse visuals
 *  - Smooth scroll via existing ScrollHighlightService, or instant jump
 *    when `prefers-reduced-motion` is set
 *  - Keyboard focus move to the target (unless the user is typing and
 *    priority is not `urgent`)
 *  - ARIA live-region announcement for screen-reader users
 *  - ESC dismisses the pulse immediately
 *
 * Usage (TS):
 *   inject(ScrollAttentionService).drawTo('#pipeline-tile', { priority: 'urgent' });
 *   inject(ScrollAttentionService).drawTo(myElementRef.nativeElement);
 */
@Injectable({ providedIn: 'root' })
export class ScrollAttentionService {
  private readonly scrollHighlight = inject(ScrollHighlightService);

  /** Single live region shared by all attention announcements. */
  private liveRegion: HTMLElement | null = null;

  /** Track the currently-pulsing element so ESC can cancel it. */
  private currentTarget: HTMLElement | null = null;
  private currentPulseClass: string | null = null;
  private escListener: ((e: KeyboardEvent) => void) | null = null;

  /**
   * Draw the user's attention to a target element.
   *
   * @param target A CSS selector, an id (with or without `#`), or an HTMLElement.
   * @param options See ScrollAttentionOptions.
   * @returns true if the target was found and the pulse scheduled; false otherwise.
   */
  drawTo(target: string | HTMLElement, options: ScrollAttentionOptions = {}): boolean {
    const element = this.resolveTarget(target);
    if (!element) {
      return false;
    }

    const priority: AttentionPriority = options.priority ?? 'normal';
    const pulseClass = options.pulseClass ?? this.defaultPulseClassFor(priority);
    const reducedMotion = this.prefersReducedMotion();

    // Cancel any prior attention pulse so two don't fight each other.
    this.dismiss();

    // Scroll. Reuse the existing utility. Use `instant` when reduced-motion is set.
    this.performScroll(element, reducedMotion);

    // Apply pulse class.
    element.classList.add(pulseClass);
    this.currentTarget = element;
    this.currentPulseClass = pulseClass;

    // Move focus unless the user is actively typing (and priority is not urgent).
    this.manageFocus(element, priority);

    // Announce for screen readers.
    if (options.announce) {
      this.announce(options.announce);
    }

    // Register ESC dismissal.
    this.attachEscListener();

    // Auto-cleanup after the pulse animation finishes (matches the CSS timing).
    const pulseDurationMs = this.pulseDurationFor(priority);
    window.setTimeout(() => {
      if (this.currentTarget === element && this.currentPulseClass === pulseClass) {
        this.dismiss();
        options.onComplete?.();
      }
    }, pulseDurationMs);

    return true;
  }

  /**
   * Cancel the current attention pulse immediately. Safe to call if nothing
   * is active. Also invoked by the ESC listener.
   */
  dismiss(): void {
    if (this.currentTarget && this.currentPulseClass) {
      this.currentTarget.classList.remove(this.currentPulseClass);
    }
    this.currentTarget = null;
    this.currentPulseClass = null;
    this.detachEscListener();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Private helpers
  // ─────────────────────────────────────────────────────────────────────────

  private resolveTarget(target: string | HTMLElement): HTMLElement | null {
    if (typeof target !== 'string') {
      return target;
    }
    const selector = target.startsWith('#') || target.startsWith('.') || target.includes('[')
      ? target
      : `#${target}`;
    return document.querySelector<HTMLElement>(selector);
  }

  private defaultPulseClassFor(priority: AttentionPriority): string {
    switch (priority) {
      case 'low':    return 'attention-pulse-low';
      case 'urgent': return 'attention-pulse-urgent';
      case 'normal':
      default:       return 'attention-pulse';
    }
  }

  /**
   * Pulse duration in ms, must match the keyframes timing in _attention.scss.
   * Kept in TS so the service can auto-cleanup the class without relying on
   * animationend events (which may not fire inside reduced-motion).
   */
  private pulseDurationFor(priority: AttentionPriority): number {
    switch (priority) {
      case 'low':    return 800;
      case 'urgent': return 1600;
      case 'normal':
      default:       return 1200;
    }
  }

  private prefersReducedMotion(): boolean {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  private performScroll(element: HTMLElement, reducedMotion: boolean): void {
    element.scrollIntoView({
      behavior: reducedMotion ? 'instant' : 'smooth',
      block: 'center',
    });
  }

  private manageFocus(element: HTMLElement, priority: AttentionPriority): void {
    const userTyping = this.isUserTyping();
    if (userTyping && priority !== 'urgent') {
      return;
    }

    // If the element is not natively focusable, make it so temporarily.
    const hadTabIndex = element.hasAttribute('tabindex');
    if (!hadTabIndex) {
      element.setAttribute('tabindex', '-1');
    }

    try {
      element.focus({ preventScroll: true });
    } catch {
      // focus() can throw in rare DOM states; silently ignore — the pulse
      // itself is the primary attention cue.
    }
  }

  private isUserTyping(): boolean {
    const active = document.activeElement;
    if (!active) return false;
    const tag = active.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if ((active as HTMLElement).isContentEditable) return true;
    return false;
  }

  private announce(message: string): void {
    const region = this.ensureLiveRegion();
    // Clear first so the same message twice still re-announces.
    region.textContent = '';
    window.setTimeout(() => { region.textContent = message; }, 20);
  }

  private ensureLiveRegion(): HTMLElement {
    if (this.liveRegion && document.body.contains(this.liveRegion)) {
      return this.liveRegion;
    }
    const region = document.createElement('div');
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'true');
    region.setAttribute('role', 'status');
    region.className = 'sr-only attention-live-region';
    // Visually hidden but screen-reader accessible.
    Object.assign(region.style, {
      position: 'absolute',
      width: '1px',
      height: '1px',
      padding: '0',
      margin: '-1px',
      overflow: 'hidden',
      clip: 'rect(0 0 0 0)',
      whiteSpace: 'nowrap',
      border: '0',
    } as CSSStyleDeclaration);
    document.body.appendChild(region);
    this.liveRegion = region;
    return region;
  }

  private attachEscListener(): void {
    if (this.escListener) return;
    const listener = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        this.dismiss();
      }
    };
    window.addEventListener('keydown', listener);
    this.escListener = listener;
  }

  private detachEscListener(): void {
    if (this.escListener) {
      window.removeEventListener('keydown', this.escListener);
      this.escListener = null;
    }
  }
}
