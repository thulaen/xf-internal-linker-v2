import { Component, DestroyRef, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import {
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
} from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

/**
 * Phase U2 / Gap 1 — Global route-change progress bar.
 *
 * Renders a thin Material indeterminate progress bar across the top of
 * the app shell whenever the Angular Router is navigating. Hides when
 * navigation completes, fails, or is cancelled.
 *
 * Uses the existing `NavigationStart` / `NavigationEnd` / `NavigationCancel`
 * / `NavigationError` events from the Router — no new timers, no polling.
 *
 * Visual rules (per FRONTEND-RULES.md):
 *   - `var(--color-primary)` only, flat colour.
 *   - 2px height, not a full bar, per GA4 / YouTube pattern.
 *   - Positioned fixed above the toolbar, `z-index: 1001` (above the
 *     offline banner's 1000 so navigation progress wins attention).
 *   - `prefers-reduced-motion` still shows the bar — presence/absence is
 *     the signal, not the animation itself. Material handles the fallback.
 */
@Component({
  selector: 'app-nav-progress-bar',
  standalone: true,
  imports: [CommonModule, MatProgressBarModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (active()) {
      <mat-progress-bar mode="indeterminate"
                        class="nav-progress-bar"
                        aria-label="Loading page"
                        role="progressbar"></mat-progress-bar>
    }
  `,
  styles: [`
    :host {
      /* Fixed so the bar overlays the top without shifting content. */
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 1001;
      pointer-events: none;
      display: block;
    }

    .nav-progress-bar {
      --mdc-linear-progress-active-indicator-height: 2px;
      --mdc-linear-progress-track-height: 2px;
      --mdc-linear-progress-active-indicator-color: var(--color-primary);
      --mdc-linear-progress-track-color: transparent;
      height: 2px;
    }
  `],
})
export class NavProgressBarComponent {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  /** True while the Router is mid-navigation. */
  readonly active = signal(false);

  constructor() {
    this.router.events
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((event) => {
        if (event instanceof NavigationStart) {
          this.active.set(true);
        } else if (
          event instanceof NavigationEnd ||
          event instanceof NavigationCancel ||
          event instanceof NavigationError
        ) {
          this.active.set(false);
        }
      });
  }
}
