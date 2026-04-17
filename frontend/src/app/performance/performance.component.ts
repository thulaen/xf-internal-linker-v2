import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatTableModule } from '@angular/material/table';
import { MatSortModule } from '@angular/material/sort';
import { MatChipsModule } from '@angular/material/chips';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration, ChartData } from 'chart.js';
import {
  PerformanceService,
  BenchmarkRun,
  BenchmarkResult,
  BenchmarkTrendPoint,
} from './performance.service';

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
    MatTableModule,
    MatSortModule,
    MatChipsModule,
    BaseChartDirective,
  ],
  templateUrl: './performance.component.html',
  styleUrls: ['./performance.component.scss'],
})
export class PerformanceComponent implements OnInit {
  private svc = inject(PerformanceService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

  latestRun: BenchmarkRun | null = null;
  isLoading = true;
  isTriggering = false;
  errorMessage = '';

  /* Summary counts */
  fastCount = 0;
  okCount = 0;
  slowCount = 0;
  lastRunAgo = '';

  /* Filter state */
  selectedLanguage = 'all';
  selectedStatus = 'all';

  /* Table */
  displayedColumns = ['status', 'language', 'extension', 'function_name', 'small', 'medium', 'large'];
  filteredResults: BenchmarkResult[] = [];

  /* Trend chart */
  trendChartData: ChartData<'line'> | null = null;
  trendChartOptions: ChartConfiguration<'line'>['options'] = {
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

  ngOnInit(): void {
    this.loadLatest();
    this.loadTrends();
  }

  loadLatest(): void {
    this.isLoading = true;
    this.svc.getLatest()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (run) => {
        this.latestRun = run;
        this.updateSummary(run);
        this.applyFilters();
        this.isLoading = false;
      },
      error: () => {
        this.errorMessage = 'No benchmark data available yet. Run your first benchmark.';
        this.isLoading = false;
      },
    });
  }

  triggerRun(): void {
    this.isTriggering = true;
    this.svc.trigger()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.isTriggering = false;
        /* Poll for completion */
        setTimeout(() => this.loadLatest(), 5000);
      },
      error: () => {
        this.isTriggering = false;
      },
    });
  }

  downloadReport(): void {
    if (!this.latestRun) return;
    this.svc.getReport(this.latestRun.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (res) => {
        const blob = new Blob([res.report], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `benchmark-report-${this.latestRun!.id}.txt`;
        a.click();
        URL.revokeObjectURL(url);
      },
    });
  }

  filterByLanguage(lang: string): void {
    this.selectedLanguage = this.selectedLanguage === lang ? 'all' : lang;
    this.applyFilters();
  }

  filterByStatus(status: string): void {
    this.selectedStatus = this.selectedStatus === status ? 'all' : status;
    this.applyFilters();
  }

  private applyFilters(): void {
    if (!this.latestRun) return;
    this.filteredResults = this.latestRun.results.filter((r) => {
      if (this.selectedLanguage !== 'all' && r.language !== this.selectedLanguage) return false;
      if (this.selectedStatus !== 'all' && r.status !== this.selectedStatus) return false;
      return true;
    });
  }

  private updateSummary(run: BenchmarkRun): void {
    const summary = run.summary_json;
    this.fastCount = summary?.fast ?? 0;
    this.okCount = summary?.ok ?? 0;
    this.slowCount = summary?.slow ?? 0;

    if (run.finished_at) {
      const diff = Date.now() - new Date(run.finished_at).getTime();
      const hours = Math.floor(diff / 3_600_000);
      const mins = Math.floor((diff % 3_600_000) / 60_000);
      this.lastRunAgo = hours > 0 ? `${hours}h ${mins}m ago` : `${mins}m ago`;
    }
  }

  private loadTrends(): void {
    this.svc.getTrends()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (points) => {
        if (points.length === 0) return;
        this.buildTrendChart(points);
      },
    });
  }

  private buildTrendChart(points: BenchmarkTrendPoint[]): void {
    const funcMap = new Map<string, { dates: string[]; values: number[] }>();

    for (const p of points) {
      const key = `${p.language}/${p.function}`;
      if (!funcMap.has(key)) {
        funcMap.set(key, { dates: [], values: [] });
      }
      const entry = funcMap.get(key)!;
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

    this.trendChartData = { labels, datasets };
  }

  formatTime(ns: number): string {
    if (ns < 1_000) return `${ns}ns`;
    if (ns < 1_000_000) return `${(ns / 1_000).toFixed(1)}us`;
    if (ns < 1_000_000_000) return `${(ns / 1_000_000).toFixed(1)}ms`;
    return `${(ns / 1_000_000_000).toFixed(2)}s`;
  }

  getResultForSize(extension: string, funcName: string, size: string): BenchmarkResult | undefined {
    return this.latestRun?.results.find(
      (r) => r.extension === extension && r.function_name === funcName && r.input_size === size
    );
  }

  get uniqueFunctions(): { extension: string; function_name: string; language: string; status: string }[] {
    const seen = new Set<string>();
    const funcs: { extension: string; function_name: string; language: string; status: string }[] = [];
    for (const r of this.filteredResults) {
      const key = `${r.extension}.${r.function_name}`;
      if (!seen.has(key)) {
        seen.add(key);
        /* Use worst status across sizes */
        const allForFunc = this.filteredResults.filter(
          (x) => x.extension === r.extension && x.function_name === r.function_name
        );
        const worstStatus = allForFunc.some((x) => x.status === 'slow')
          ? 'slow'
          : allForFunc.some((x) => x.status === 'ok')
            ? 'ok'
            : 'fast';
        funcs.push({
          extension: r.extension,
          function_name: r.function_name,
          language: r.language,
          status: worstStatus,
        });
      }
    }
    return funcs;
  }
}
