import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration, ChartData } from 'chart.js';
import { timer } from 'rxjs';
import {
  PerformanceService,
  BenchmarkRun,
  BenchmarkResult,
  BenchmarkTrendPoint,
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
    BaseChartDirective,
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

  // Trend chart data — set once after the trends fetch resolves.
  readonly trendChartData = signal<ChartData<'line'> | null>(null);
  readonly trendChartOptions: ChartConfiguration<'line'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true, position: 'top' },
      tooltip: { mode: 'index', intersect: false },
    },
    scales: {
      x: { title: { display: true, text: 'Date' } },
      y: { title: { display: true, text: 'Time (ms)' }, beginAtZero: true },
    },
  };

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
    this.svc.getTrends()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (points) => {
          if (points.length === 0) return;
          this.trendChartData.set(buildTrendChart(points));
        },
        error: (err) => console.warn('loadTrends failed', err),
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
 * Build a Chart.js dataset from raw trend points. Top-level pure
 * function — easy to test in isolation, doesn't capture component
 * state, doesn't allocate fields.
 */
function buildTrendChart(points: BenchmarkTrendPoint[]): ChartData<'line'> {
  const funcMap = new Map<string, { dates: string[]; values: number[] }>();
  for (const p of points) {
    const key = `${p.language}/${p.function}`;
    let entry = funcMap.get(key);
    if (!entry) {
      entry = { dates: [], values: [] };
      funcMap.set(key, entry);
    }
    entry.dates.push(p.date);
    entry.values.push(p.mean_ns / 1_000_000); /* ns → ms */
  }
  const labels = [...new Set(points.map((p) => p.date))].sort();
  const datasets = [...funcMap.entries()].slice(0, 10).map(([key, data]) => ({
    label: key,
    data: data.values,
    fill: false,
    tension: 0.3,
  }));
  return { labels, datasets };
}
