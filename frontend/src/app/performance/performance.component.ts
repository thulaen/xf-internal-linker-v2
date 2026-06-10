import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import type { EChartsOption } from 'echarts';
import { timer } from 'rxjs';
import { EchartsDirective } from '../shared/charts/echarts.directive';
import { PeHelperDirective } from '../shared/directives/pe-helper.directive';
import { gscChartBase, gscPalette, token, withAlpha } from '../shared/charts/echarts-theme';
import {
  PerformanceService,
  BenchmarkRun,
  BenchmarkResult,
  BenchmarkTrendPoint,
  Stage2PathStatus,
} from './performance.service';

/** Three input sizes the benchmark suite emits per function. */
const INPUT_SIZES = ['small', 'medium', 'large'] as const;
type InputSize = typeof INPUT_SIZES[number];

interface UniqueFunction {
  extension: string;
  function_name: string;
  language: string;
  status: 'fast' | 'ok' | 'slow';
}

@Component({
  selector: 'app-performance',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatChipsModule,
    EchartsDirective,
    PeHelperDirective,
  ],
  templateUrl: './performance.component.html',
  styleUrls: ['./performance.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PerformanceComponent implements OnInit {
  private svc = inject(PerformanceService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

  // Server-truth: the latest benchmark run. Every derived value below
  // (summary counts, filtered results, function dedupe, lookup map)
  // recomputes automatically when this signal updates.
  readonly latestRun = signal<BenchmarkRun | null>(null);
  readonly isLoading = signal(true);
  readonly isTriggering = signal(false);
  readonly errorMessage = signal('');

  // Filter state — drives the `filteredResults` computed below.
  readonly selectedLanguage = signal<'all' | 'cpp' | 'python'>('all');
  readonly selectedStatus = signal<'all' | 'fast' | 'ok' | 'slow'>('all');

  // FR-247 — Stage-2 cpp/python pathway status. Polled once on init;
  // a future commit can promote to a 30-second refresh signal if
  // operators want live drift visibility. See
  // docs/specs/fr247-fast-path-observability.md.
  readonly stage2PathStatus = signal<Stage2PathStatus | null>(null);

  // Trend chart option — set once after the trends fetch resolves. `null`
  // until data arrives so the template shows the empty state, never a blank
  // chart implying "all good".
  readonly trendChartData = signal<EChartsOption | null>(null);

  // Truthful state for the trend chart card. The card is always shown so the
  // operator never sees a missing panel; this signal drives whether the body
  // is the live chart, a loading spinner, an empty "no history yet" note, or
  // a blocked "could not load" note. Never a blank chart implying "all good".
  readonly trendState = signal<'loading' | 'ready' | 'empty' | 'error'>('loading');

  /** Sizes exposed to the template so the three-cell row collapses to a `@for`. */
  readonly sizes = INPUT_SIZES;

  // ── Derived state (replaces imperative updateSummary / applyFilters) ──

  readonly fastCount = computed(() => this.latestRun()?.summary_json?.fast ?? 0);
  readonly okCount = computed(() => this.latestRun()?.summary_json?.ok ?? 0);
  readonly slowCount = computed(() => this.latestRun()?.summary_json?.slow ?? 0);

  readonly lastRunAgo = computed(() => {
    const run = this.latestRun();
    if (!run?.finished_at) return '';
    const diff = Date.now() - new Date(run.finished_at).getTime();
    const hours = Math.floor(diff / 3_600_000);
    const mins = Math.floor((diff % 3_600_000) / 60_000);
    return hours > 0 ? `${hours}h ${mins}m ago` : `${mins}m ago`;
  });

  readonly filteredResults = computed<BenchmarkResult[]>(() => {
    const run = this.latestRun();
    if (!run) return [];
    const lang = this.selectedLanguage();
    const status = this.selectedStatus();
    return run.results.filter((r) => {
      if (lang !== 'all' && r.language !== lang) return false;
      if (status !== 'all' && r.status !== status) return false;
      return true;
    });
  });

  /**
   * Map keyed by `${extension}.${function_name}.${input_size}` for O(1)
   * lookups from the template. Replaces the previous per-cell linear
   * `find()` over `latestRun.results` — with M rows × 6 cells × N
   * results that was O(M × N) per render. Now O(N) once when results
   * change, then O(1) per cell.
   */
  private readonly resultsBySize = computed(() => {
    const run = this.latestRun();
    if (!run) return new Map<string, BenchmarkResult>();
    const map = new Map<string, BenchmarkResult>();
    for (const r of run.results) {
      map.set(`${r.extension}.${r.function_name}.${r.input_size}`, r);
    }
    return map;
  });

  /**
   * Dedupe by extension+function_name; pick the worst status across
   * sizes ("slow" beats "ok" beats "fast"). Computed instead of getter
   * so the O(n²) scan only runs when filteredResults changes, not on
   * every binding read.
   */
  readonly uniqueFunctions = computed<UniqueFunction[]>(() => {
    const filtered = this.filteredResults();
    const seen = new Map<string, UniqueFunction>();
    for (const r of filtered) {
      const key = `${r.extension}.${r.function_name}`;
      const existing = seen.get(key);
      const candidate: UniqueFunction = {
        extension: r.extension,
        function_name: r.function_name,
        language: r.language,
        status: r.status as 'fast' | 'ok' | 'slow',
      };
      if (!existing) {
        seen.set(key, candidate);
        continue;
      }
      // Worst status wins (slow > ok > fast). Single pass over the
      // filtered set, no nested filter — O(n) total instead of the
      // previous getter's O(n²).
      if (worstStatus(existing.status, candidate.status) !== existing.status) {
        seen.set(key, { ...existing, status: candidate.status });
      }
    }
    return [...seen.values()];
  });

  ngOnInit(): void {
    this.loadLatest();
    this.loadTrends();
    this.loadStage2PathStatus();
  }

  /** FR-247 — fetch the cpp/python pathway counter snapshot. */
  loadStage2PathStatus(): void {
    this.svc.getStage2PathStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status) => this.stage2PathStatus.set(status),
        error: (err) => console.warn('FR-247 status fetch failed', err),
      });
  }

  loadLatest(): void {
    this.isLoading.set(true);
    this.errorMessage.set('');
    this.svc.getLatest()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (run) => {
          this.latestRun.set(run);
          this.isLoading.set(false);
        },
        error: () => {
          this.errorMessage.set('No benchmark data available yet. Run your first benchmark.');
          this.isLoading.set(false);
        },
      });
  }

  triggerRun(): void {
    this.isTriggering.set(true);
    this.svc.trigger()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.isTriggering.set(false);
          // Wait for the worker to finish before re-fetching. `timer`
          // honours route teardown via takeUntilDestroyed — the previous
          // bare `setTimeout` was uncancellable and could fire after
          // the user had navigated away.
          timer(5000)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe(() => this.loadLatest());
        },
        error: () => {
          this.isTriggering.set(false);
        },
      });
  }

  downloadReport(): void {
    const run = this.latestRun();
    if (!run) return;
    this.svc.getReport(run.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          const blob = new Blob([res.report], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `benchmark-report-${run.id}.txt`;
          a.click();
          URL.revokeObjectURL(url);
        },
        error: (err) => {
          console.warn('downloadReport failed', err);
          // No MatSnackBar injected here; surface failure in the
          // existing errorMessage signal so the page shows it.
          this.errorMessage.set('Failed to download report');
        },
      });
  }

  filterByLanguage(lang: string): void {
    const next = this.selectedLanguage() === lang ? 'all' : lang;
    this.selectedLanguage.set(next as 'all' | 'cpp' | 'python');
  }

  filterByStatus(status: string): void {
    const next = this.selectedStatus() === status ? 'all' : status;
    this.selectedStatus.set(next as 'all' | 'fast' | 'ok' | 'slow');
  }

  private loadTrends(): void {
    this.trendState.set('loading');
    this.svc.getTrends()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (points) => {
          if (points.length === 0) {
            this.trendChartData.set(null);
            this.trendState.set('empty');
            return;
          }
          this.trendChartData.set(buildTrendChart(points));
          this.trendState.set('ready');
        },
        error: (err) => {
          console.warn('loadTrends failed', err);
          this.trendChartData.set(null);
          this.trendState.set('error');
        },
      });
  }

  formatTime(ns: number): string {
    if (ns < 1_000) return `${ns}ns`;
    if (ns < 1_000_000) return `${(ns / 1_000).toFixed(1)}us`;
    if (ns < 1_000_000_000) return `${(ns / 1_000_000).toFixed(1)}ms`;
    return `${(ns / 1_000_000_000).toFixed(2)}s`;
  }

  /** O(1) lookup against the precomputed map. */
  getResultForSize(extension: string, funcName: string, size: InputSize): BenchmarkResult | undefined {
    return this.resultsBySize().get(`${extension}.${funcName}.${size}`);
  }
}

/** "slow" > "ok" > "fast". Returns the worse of the two. */
function worstStatus(a: string, b: string): string {
  if (a === 'slow' || b === 'slow') return 'slow';
  if (a === 'ok' || b === 'ok') return 'ok';
  return 'fast';
}

/**
 * Build an ECharts multi-line option from raw trend points. Top-level pure
 * function — easy to test in isolation, doesn't capture component state.
 * One line per `language/function`, up to 10, plotting mean time in ms over
 * the sorted set of dates.
 */
function buildTrendChart(points: BenchmarkTrendPoint[]): EChartsOption {
  const funcMap = new Map<string, Map<string, number>>();
  for (const p of points) {
    const key = `${p.language}/${p.function}`;
    let entry = funcMap.get(key);
    if (!entry) {
      entry = new Map<string, number>();
      funcMap.set(key, entry);
    }
    entry.set(p.date, p.mean_ns / 1_000_000); /* ns → ms */
  }
  const labels = [...new Set(points.map((p) => p.date))].sort();
  const base = gscChartBase();
  const series = [...funcMap.entries()].slice(0, 10).map(([key, byDate]) => ({
    name: key,
    type: 'line' as const,
    smooth: true,
    showSymbol: false,
    // Align each series to the shared date axis; gaps become null points.
    data: labels.map((d) => byDate.get(d) ?? null),
  }));
  const muted = token('--color-text-muted');
  return {
    ...base,
    color: gscPalette(),
    tooltip: { ...(base['tooltip'] as object), trigger: 'axis' },
    legend: { ...(base['legend'] as object), type: 'scroll', data: series.map((s) => s.name) },
    xAxis: {
      type: 'category',
      data: labels,
      name: 'Date',
      axisLine: { lineStyle: { color: token('--color-border') } },
      axisLabel: { color: muted, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: 'Time (ms)',
      min: 0,
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: withAlpha(muted, 0.1) } },
    },
    series,
  };
}
