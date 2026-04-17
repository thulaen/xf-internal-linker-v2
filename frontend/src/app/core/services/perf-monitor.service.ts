import { Injectable, isDevMode, signal } from '@angular/core';

/**
 * Phase OB — combined performance-monitor service. Two gaps, one
 * service because they share the same data model (a bounded ring
 * buffer of "something happened" events):
 *
 *   - Gap 134 Long-task observer  (PerformanceObserver for tasks >50ms)
 *   - Gap 135 Memory-leak alarm   (polls performance.memory in dev)
 *
 * Consumers — most notably the Debug Overlay in Gap 133 — read the
 * `longTasks` and `memorySamples` signals to render live panels.
 *
 * Privacy: all data stays in memory. Nothing hits the network. The
 * ring buffers cap out at `MAX_ENTRIES` so a runaway render loop
 * can't OOM the browser tab.
 */

const MAX_ENTRIES = 200;
const MEMORY_POLL_MS = 10_000;
const LONG_TASK_THRESHOLD_MS = 50;
const MEMORY_ALARM_THRESHOLD = 0.85; // 85% of the heap limit

export interface LongTaskEntry {
  at: number;
  duration: number;
  /** Attribution container where available — e.g. 'self' or 'same-origin-ancestor'. */
  attribution: string;
}

export interface MemorySample {
  at: number;
  usedHeapMb: number;
  totalHeapMb: number;
  heapLimitMb: number;
  /** usedHeap / heapLimit — alarm when >= MEMORY_ALARM_THRESHOLD. */
  pressure: number;
}

/** Extended Performance interface for the non-standard memory field. */
interface PerformanceWithMemory extends Performance {
  memory?: {
    jsHeapSizeLimit: number;
    totalJSHeapSize: number;
    usedJSHeapSize: number;
  };
}

@Injectable({ providedIn: 'root' })
export class PerfMonitorService {
  readonly longTasks = signal<readonly LongTaskEntry[]>([]);
  readonly memorySamples = signal<readonly MemorySample[]>([]);
  readonly memoryAlarm = signal<boolean>(false);

  private started = false;
  private longTaskObserver: PerformanceObserver | null = null;
  private memoryTimer: ReturnType<typeof setInterval> | null = null;

  start(): void {
    if (this.started) return;
    this.started = true;
    this.startLongTaskObserver();
    this.startMemoryPoll();
  }

  stop(): void {
    this.started = false;
    this.longTaskObserver?.disconnect();
    this.longTaskObserver = null;
    if (this.memoryTimer) clearInterval(this.memoryTimer);
    this.memoryTimer = null;
  }

  /** Manual reset — the Debug Overlay's "clear" button. */
  clear(): void {
    this.longTasks.set([]);
    this.memorySamples.set([]);
    this.memoryAlarm.set(false);
  }

  // ── long tasks (Gap 134) ──────────────────────────────────────────

  private startLongTaskObserver(): void {
    if (typeof PerformanceObserver === 'undefined') return;
    // `longtask` entries are emitted when a script blocks the main
    // thread for > 50ms. Firefox + Safari don't support it yet; the
    // try/catch swallows "unsupported entryType" there.
    try {
      this.longTaskObserver = new PerformanceObserver((list) => {
        const additions: LongTaskEntry[] = [];
        for (const entry of list.getEntries()) {
          if (entry.duration < LONG_TASK_THRESHOLD_MS) continue;
          const attribution =
            (entry as PerformanceEntry & { attribution?: { containerName?: string }[] })
              .attribution?.[0]?.containerName ?? 'self';
          additions.push({
            at: entry.startTime + performance.timeOrigin,
            duration: entry.duration,
            attribution,
          });
        }
        if (additions.length === 0) return;
        this.push(this.longTasks, additions);
      });
      this.longTaskObserver.observe({ type: 'longtask', buffered: true });
    } catch {
      this.longTaskObserver = null;
    }
  }

  // ── memory alarm (Gap 135) ─────────────────────────────────────────

  private startMemoryPoll(): void {
    const perf = performance as PerformanceWithMemory;
    if (!perf.memory) {
      // Chromium-only API — Firefox/Safari just skip this loop.
      return;
    }
    // Gate heavy polling to dev mode so a prod user never runs this.
    // (In prod we still keep the longTaskObserver — it's free and
    // yields real user data via the web-vitals pipeline instead.)
    if (!isDevMode()) return;
    const sample = () => {
      const m = perf.memory;
      if (!m) return;
      const used = m.usedJSHeapSize / (1024 * 1024);
      const total = m.totalJSHeapSize / (1024 * 1024);
      const limit = m.jsHeapSizeLimit / (1024 * 1024);
      const pressure = limit > 0 ? used / limit : 0;
      const entry: MemorySample = {
        at: Date.now(),
        usedHeapMb: used,
        totalHeapMb: total,
        heapLimitMb: limit,
        pressure,
      };
      this.push(this.memorySamples, [entry]);
      if (pressure >= MEMORY_ALARM_THRESHOLD) {
        this.memoryAlarm.set(true);
      }
    };
    sample();
    this.memoryTimer = setInterval(sample, MEMORY_POLL_MS);
  }

  // ── internals ──────────────────────────────────────────────────────

  private push<T>(
    target: { set(v: readonly T[]): void; (): readonly T[] },
    additions: T[],
  ): void {
    const current = (target as unknown as () => readonly T[])();
    const next = [...current, ...additions];
    if (next.length > MAX_ENTRIES) {
      next.splice(0, next.length - MAX_ENTRIES);
    }
    (target as unknown as { set(v: readonly T[]): void }).set(next);
  }
}
