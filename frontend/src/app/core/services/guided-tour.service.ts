import { Injectable, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D2 / Gap 70 — Guided Tour state.
 *
 * Holds the active tour, current step index, and a "completed" flag in
 * localStorage. A tour is a flat list of steps; each step pins to a CSS
 * selector that the GuidedTourComponent will spotlight.
 *
 * The toolbar 🗺 "replay tour" button invokes `start()`, which clears
 * the completed flag and shows step 0 again. First-visit auto-launch is
 * NOT in scope here — that lives in the future onboarding state machine
 * (Gap 150).
 */

export interface TourStep {
  /** CSS selector of the element to spotlight. */
  selector: string;
  /** Short noun-phrase title shown in the tour bubble. */
  title: string;
  /** One- or two-sentence body of the step. */
  body: string;
  /** Where to anchor the bubble relative to the target. */
  placement?: 'top' | 'bottom' | 'left' | 'right';
}

export interface Tour {
  id: string;
  steps: readonly TourStep[];
}

const COMPLETED_KEY_PREFIX = 'xfil_tour_completed.';

@Injectable({ providedIn: 'root' })
export class GuidedTourService {
  private readonly _activeTour = signal<Tour | null>(null);
  private readonly _stepIndex = signal<number>(0);

  /** Reactive views — components consume these to render. */
  readonly activeTour = this._activeTour.asReadonly();
  readonly stepIndex = this._stepIndex.asReadonly();
  readonly active$ = toObservable(this._activeTour);

  /** Start (or restart) a tour. Clears any "completed" flag for that
   *  tour id so the spotlight UI shows. */
  start(tour: Tour): void {
    if (!tour.steps || tour.steps.length === 0) return;
    try {
      localStorage.removeItem(COMPLETED_KEY_PREFIX + tour.id);
    } catch {
      // No-op.
    }
    this._activeTour.set(tour);
    this._stepIndex.set(0);
  }

  /** Has the user already completed (or skipped) this tour at least once? */
  hasCompleted(tourId: string): boolean {
    try {
      return localStorage.getItem(COMPLETED_KEY_PREFIX + tourId) === '1';
    } catch {
      return false;
    }
  }

  next(): void {
    const tour = this._activeTour();
    if (!tour) return;
    const i = this._stepIndex();
    if (i + 1 >= tour.steps.length) {
      this.finish();
    } else {
      this._stepIndex.set(i + 1);
    }
  }

  previous(): void {
    const i = this._stepIndex();
    if (i <= 0) return;
    this._stepIndex.set(i - 1);
  }

  /** Skip the rest of the tour. Marks completed. */
  skip(): void {
    this.finish();
  }

  /** Finish the tour and remember that it was shown. */
  private finish(): void {
    const tour = this._activeTour();
    if (tour) {
      try {
        localStorage.setItem(COMPLETED_KEY_PREFIX + tour.id, '1');
      } catch {
        // No-op.
      }
    }
    this._activeTour.set(null);
    this._stepIndex.set(0);
  }
}

/**
 * The default dashboard tour. Lives here (not in the component file) so
 * it can be reused by both the toolbar replay button and the future
 * first-visit auto-launch.
 */
export const DASHBOARD_TOUR: Tour = {
  id: 'dashboard-v1',
  steps: [
    {
      selector: 'app-mission-brief',
      title: 'Mission Brief',
      body: 'Your three-sentence morning briefing: yesterday, today, and what to watch. Refreshes every 15 minutes.',
      placement: 'bottom',
    },
    {
      selector: 'app-status-story',
      title: 'Status Story',
      body: "Plain-English summary of what's going on right now. Refreshes every 5 minutes.",
      placement: 'bottom',
    },
    {
      selector: 'app-priority-action-queue',
      title: 'Do these first',
      body: 'A ranked top-3 list of the most important things to do in the next 30 minutes. Click "Do this" to jump in.',
      placement: 'bottom',
    },
    {
      selector: 'app-health-score-dial',
      title: 'Health Score',
      body: 'One number from 0 to 100 summarising overall health. Click "Drill into Health" for the full breakdown.',
      placement: 'left',
    },
    {
      selector: 'app-trend-deltas',
      title: 'Today vs Yesterday',
      body: 'Quick deltas on your KPIs. Green is the good direction; red is the bad one (broken links going up = bad).',
      placement: 'top',
    },
    {
      selector: 'app-color-legend',
      title: 'Color key',
      body: 'When in doubt, the colors mean: green = good, amber = warning, red = broken, blue = info, grey = idle.',
      placement: 'top',
    },
  ],
};
