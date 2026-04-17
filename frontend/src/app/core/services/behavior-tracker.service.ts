import { Injectable, inject } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

/**
 * Phase D2 / Gap 73 — Lightweight client-side behavior tracker.
 *
 * Records which dashboard route the user visits FIRST in each daily
 * session. The Behavioral Nudge card reads this history and suggests
 * the user's typical next move ("Yesterday you usually checked Alerts
 * first").
 *
 * Privacy: data lives only in the user's localStorage. Nothing leaves
 * the browser. Stores at most the last 14 days. Records only the first
 * navigation per local day to keep noise low.
 *
 * Routes recorded are NORMALISED to top-level segments (e.g. `/review`,
 * `/health`, `/jobs`) so per-detail variations like `/review?status=…`
 * collapse together.
 */

const HISTORY_KEY = 'xfil_first_visit_history';
const MAX_DAYS = 14;

interface DailyVisit {
  /** YYYY-MM-DD in local time. */
  date: string;
  /** Top-level route, e.g. `/review`. */
  route: string;
}

@Injectable({ providedIn: 'root' })
export class BehaviorTrackerService {
  private readonly router = inject(Router);
  private started = false;

  /** Wire once from app bootstrap. Subsequent calls are no-ops. */
  start(): void {
    if (this.started) return;
    this.started = true;
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe((e) => {
        const url = (e as NavigationEnd).urlAfterRedirects ?? '';
        const route = this.normaliseRoute(url);
        if (!route || route === '/dashboard') return; // skip the dashboard itself
        this.recordVisit(route);
      });
  }

  /** Read the most-visited first-route across the last `MAX_DAYS` days.
   *  Returns null if we don't yet have at least 3 days of data — not
   *  enough to make a suggestion. */
  getMostVisitedRoute(): { route: string; count: number; days: number } | null {
    const history = this.readHistory();
    if (history.length < 3) return null;
    const tally = new Map<string, number>();
    for (const v of history) {
      tally.set(v.route, (tally.get(v.route) ?? 0) + 1);
    }
    let best: { route: string; count: number } | null = null;
    for (const [route, count] of tally) {
      if (!best || count > best.count) {
        best = { route, count };
      }
    }
    if (!best) return null;
    return { route: best.route, count: best.count, days: history.length };
  }

  // ── internals ──────────────────────────────────────────────────────

  private normaliseRoute(url: string): string {
    // Strip query and fragment.
    const noQs = url.split('?')[0].split('#')[0];
    // Top-level segment only.
    const parts = noQs.split('/').filter(Boolean);
    if (parts.length === 0) return '/';
    return '/' + parts[0];
  }

  private recordVisit(route: string): void {
    const today = this.todayKey();
    const history = this.readHistory();
    // Already recorded this day? Skip.
    if (history.some((v) => v.date === today)) return;
    history.push({ date: today, route });
    // Keep only the last MAX_DAYS distinct days.
    history.sort((a, b) => a.date.localeCompare(b.date));
    while (history.length > MAX_DAYS) history.shift();
    this.persistHistory(history);
  }

  private readHistory(): DailyVisit[] {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw) as DailyVisit[];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  private persistHistory(history: DailyVisit[]): void {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch {
      // Private mode — best effort.
    }
  }

  private todayKey(): string {
    const d = new Date();
    const y = d.getFullYear();
    const m = (d.getMonth() + 1).toString().padStart(2, '0');
    const dd = d.getDate().toString().padStart(2, '0');
    return `${y}-${m}-${dd}`;
  }
}
