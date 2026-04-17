import { Injectable, isDevMode, signal } from '@angular/core';

/**
 * Phase OB / Gap 136 — Network-waterfall capture for the Debug Overlay.
 *
 * Uses `PerformanceObserver` with `type: 'resource'` to capture every
 * resource (fetch, xhr, image, script, stylesheet) the page loads,
 * and keeps a bounded ring buffer that the debug-overlay renders as
 * a waterfall.
 *
 * Why not the DevTools Network tab: users with a bug report ZIP
 * can't share their devtools. Our in-app panel lives alongside the
 * error-log so diagnostic data is one click away.
 *
 * Only starts in dev mode — noise-free prod + smaller prod bundles.
 */

const MAX_ENTRIES = 200;

export interface NetworkEntry {
  id: string;
  startedAt: number;   // ms since page-load
  duration: number;    // ms
  initiatorType: string;
  url: string;
  status: 'ok' | 'failed' | 'cached';
  transferSizeKb: number;
}

@Injectable({ providedIn: 'root' })
export class NetworkWaterfallService {
  readonly entries = signal<readonly NetworkEntry[]>([]);

  private started = false;
  private observer: PerformanceObserver | null = null;

  start(): void {
    if (this.started) return;
    this.started = true;
    if (!isDevMode()) return; // prod = no capture
    if (typeof PerformanceObserver === 'undefined') return;
    try {
      this.observer = new PerformanceObserver((list) => {
        const additions: NetworkEntry[] = [];
        for (const entry of list.getEntries()) {
          const r = entry as PerformanceResourceTiming;
          additions.push({
            id: (r.name + '|' + r.startTime.toFixed(3)),
            startedAt: r.startTime,
            duration: r.duration,
            initiatorType: r.initiatorType,
            url: this.shortenUrl(r.name),
            status: r.transferSize === 0 && r.decodedBodySize > 0 ? 'cached' : 'ok',
            transferSizeKb: (r.transferSize || 0) / 1024,
          });
        }
        if (additions.length === 0) return;
        const next = [...this.entries(), ...additions];
        if (next.length > MAX_ENTRIES) next.splice(0, next.length - MAX_ENTRIES);
        this.entries.set(next);
      });
      this.observer.observe({ type: 'resource', buffered: true });
    } catch {
      this.observer = null;
    }
  }

  stop(): void {
    this.started = false;
    this.observer?.disconnect();
    this.observer = null;
  }

  clear(): void {
    this.entries.set([]);
  }

  private shortenUrl(url: string): string {
    try {
      const u = new URL(url);
      if (u.origin === location.origin) return u.pathname + u.search;
      return url;
    } catch {
      return url;
    }
  }
}
