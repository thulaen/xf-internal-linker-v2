import { Injectable, computed, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';

/**
 * Phase GB / Gap 150 — Onboarding state machine.
 *
 * Generic per-milestone tracker so we never re-show an onboarding
 * element the user has already dismissed or completed. Works for:
 *
 *   • Tours (delegated here from GuidedTourService)
 *   • One-shot hint cards ("first-notification-opened")
 *   • Discovery callouts ("discovered-calm-mode")
 *   • Feature-gate acknowledgements ("ack-destructive-actions")
 *
 * A "milestone" is just a string id. State is stored under
 * `onb.<id> = 1` in localStorage. Three public signals:
 *   • done()         → Set of completed ids (reactive)
 *   • progress()     → { done, total } when a milestone set is declared
 *   • allDone(ids)   → computed helper for checklists
 *
 * Conflict with GuidedTourService: that service already writes
 * `xfil_tour_completed.<id>`. This service exposes helpers that bridge
 * both namespaces so the Preference Center can show a single unified
 * list without double-bookkeeping.
 */

const NS = 'onb.';
const TOUR_NS = 'xfil_tour_completed.';

@Injectable({ providedIn: 'root' })
export class OnboardingStateService {
  private doc = inject(DOCUMENT);

  /** Every completed milestone id the service knows about (both namespaces). */
  private readonly _done = signal<ReadonlySet<string>>(new Set());
  readonly done = this._done.asReadonly();

  /** Last-declared catalogue of milestones — used by the progress meter. */
  private readonly _catalogue = signal<readonly string[]>([]);
  readonly progress = computed(() => {
    const cat = this._catalogue();
    const set = this._done();
    if (cat.length === 0) return { done: 0, total: 0, percent: 0 };
    const done = cat.filter((id) => set.has(id)).length;
    return {
      done,
      total: cat.length,
      percent: Math.round((done / cat.length) * 100),
    };
  });

  constructor() {
    this._done.set(this.loadAll());
  }

  /** Declare the list of milestones the app cares about (for the
   *  progress meter + preference-center checklist). */
  registerCatalogue(ids: readonly string[]): void {
    this._catalogue.set(ids);
  }

  isDone(id: string): boolean {
    return this._done().has(id);
  }

  markDone(id: string): void {
    if (this._done().has(id)) return;
    const next = new Set(this._done());
    next.add(id);
    this._done.set(next);
    try {
      this.doc.defaultView?.localStorage.setItem(NS + id, '1');
    } catch {
      /* QuotaExceeded — in-memory state remains authoritative */
    }
  }

  /** Revoke a single milestone — "show this again next visit". */
  reset(id: string): void {
    const next = new Set(this._done());
    if (!next.delete(id)) return;
    this._done.set(next);
    try {
      this.doc.defaultView?.localStorage.removeItem(NS + id);
      // Also clear any guided-tour completion flag under the legacy key.
      this.doc.defaultView?.localStorage.removeItem(TOUR_NS + id);
    } catch {
      /* ignore */
    }
  }

  /** Revoke EVERY tracked milestone — wired to the preference-center
   *  "Restart all onboarding" button. */
  resetAll(): void {
    const ls = this.doc.defaultView?.localStorage;
    if (!ls) {
      this._done.set(new Set());
      return;
    }
    try {
      const toRemove: string[] = [];
      for (let i = 0; i < ls.length; i++) {
        const k = ls.key(i);
        if (!k) continue;
        if (k.startsWith(NS) || k.startsWith(TOUR_NS)) toRemove.push(k);
      }
      for (const k of toRemove) ls.removeItem(k);
    } catch {
      /* ignore */
    }
    this._done.set(new Set());
  }

  allDone(ids: readonly string[]): boolean {
    const set = this._done();
    return ids.every((id) => set.has(id));
  }

  /** Load completed ids from both namespaces at boot. */
  private loadAll(): Set<string> {
    const out = new Set<string>();
    try {
      const ls = this.doc.defaultView?.localStorage;
      if (!ls) return out;
      for (let i = 0; i < ls.length; i++) {
        const k = ls.key(i);
        if (!k) continue;
        if (k.startsWith(NS) && ls.getItem(k) === '1') {
          out.add(k.slice(NS.length));
        } else if (k.startsWith(TOUR_NS) && ls.getItem(k) === '1') {
          out.add(k.slice(TOUR_NS.length));
        }
      }
    } catch {
      /* ignore */
    }
    return out;
  }
}

/**
 * Known milestones — register this at bootstrap so the progress meter
 * knows how many exist. Extend freely; adding an id never forces a
 * migration because unknown ids are "not done yet".
 */
export const ONBOARDING_CATALOGUE: readonly string[] = [
  'dashboard-v1',               // the existing DASHBOARD_TOUR id
  'first-notification-seen',
  'discovered-calm-mode',
  'discovered-command-palette',
  'discovered-glossary',
  'first-suggestion-approved',
  'ack-destructive-actions',
  'first-preference-visit',
];
