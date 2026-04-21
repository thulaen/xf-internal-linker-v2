import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { catchError, of, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';

/**
 * Phase OB / Gap 130 — Real User Monitoring summary card.
 *
 * Calls the new `/api/rum/summary/` endpoint every 5 minutes and
 * renders the five Core Web Vitals with their p75 + sample count.
 * A colour dot next to each value shows how it scores against
 * Google's thresholds (good / needs-improvement / poor).
 *
 * Placement: the dashboard's "Mission Critical" area or the
 * Performance page — parent decides. Self-hides when the backend
 * hasn't seen any web-vitals telemetry yet (N = 0).
 */

interface MetricStats {
  p50: number;
  p75: number;
  p95: number;
  n: number;
}

interface RumSummary {
  window_hours: number;
  metrics: Record<string, MetricStats>;
  routes: Record<string, Record<string, MetricStats>>;
}

const THRESHOLDS: Record<string, { good: number; poor: number; unit: string }> = {
  LCP: { good: 2500, poor: 4000, unit: 'ms' },
  INP: { good: 200, poor: 500, unit: 'ms' },
  FCP: { good: 1800, poor: 3000, unit: 'ms' },
  TTFB: { good: 800, poor: 1800, unit: 'ms' },
  CLS: { good: 0.1, poor: 0.25, unit: '' },
};

@Component({
  selector: 'app-rum-summary',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DecimalPipe,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <mat-card class="rs-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="rs-avatar">monitoring</mat-icon>
        <mat-card-title>Real User Monitoring</mat-card-title>
        <mat-card-subtitle>
          Web Vitals · last 24h
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (loading() && !summary()) {
          <div class="rs-spinner"><mat-spinner diameter="24" /></div>
        } @else if (summary(); as s) {
          @if (totalSamples(s) === 0) {
            <p class="rs-empty">
              No real-user samples yet. Samples land in
              <code>/api/telemetry/web-vitals/</code> from every active session.
            </p>
          } @else {
            <dl class="rs-grid">
              @for (name of metricOrder; track name) {
                @if (s.metrics[name]; as m) {
                  <div class="rs-row">
                    <dt>
                      <span class="rs-dot" [class]="'rs-' + gradeOf(name, m.p75)"></span>
                      {{ name }}
                    </dt>
                    <dd class="rs-val">
                      {{ m.p75 | number:'1.0-1' }}{{ unitOf(name) }}
                      <span class="rs-n">· {{ m.n }} samples</span>
                    </dd>
                  </div>
                }
              }
            </dl>
          }
        } @else {
          <p class="rs-empty">Could not load RUM summary.</p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .rs-card { height: 100%; }
    .rs-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .rs-spinner {
      display: flex;
      justify-content: center;
      padding: 12px 0;
    }
    .rs-empty {
      margin: 0;
      font-size: 12px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
    .rs-grid {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin: 0;
    }
    .rs-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 10px;
      border-radius: 4px;
    }
    .rs-row:nth-child(odd) { background: var(--color-bg-faint); }
    dt {
      font-weight: 500;
      font-size: 12px;
      color: var(--color-text-primary);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    dd {
      margin: 0;
      font-variant-numeric: tabular-nums;
      color: var(--color-text-primary);
      font-size: 13px;
    }
    .rs-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .rs-good { background: var(--color-success, #1e8e3e); }
    .rs-warn { background: var(--color-warning, #f9ab00); }
    .rs-bad  { background: var(--color-error, #d93025); }
    .rs-n {
      margin-left: 4px;
      font-size: 11px;
      color: var(--color-text-secondary);
    }
  `],
})
export class RumSummaryComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private readonly visibilityGate = inject(VisibilityGateService);

  readonly summary = signal<RumSummary | null>(null);
  readonly loading = signal(false);
  readonly metricOrder = ['LCP', 'INP', 'CLS', 'FCP', 'TTFB'] as const;

  ngOnInit(): void {
    // 5-minute poll, gated by `VisibilityGateService` so hidden tabs
    // and signed-out sessions do not hit the API. See
    // docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(0, 5 * 60 * 1000).pipe(
          switchMap(() => {
            this.loading.set(true);
            return this.http
              .get<RumSummary>('/api/rum/summary/')
              .pipe(catchError(() => of<RumSummary | null>(null)));
          }),
        ),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((res) => {
        this.loading.set(false);
        if (res) this.summary.set(res);
      });
  }

  totalSamples(s: RumSummary): number {
    return Object.values(s.metrics).reduce((acc, m) => acc + (m?.n ?? 0), 0);
  }

  unitOf(name: string): string {
    return THRESHOLDS[name]?.unit ?? '';
  }

  gradeOf(name: string, p75: number): 'good' | 'warn' | 'bad' {
    const t = THRESHOLDS[name];
    if (!t) return 'good';
    if (p75 <= t.good) return 'good';
    if (p75 <= t.poor) return 'warn';
    return 'bad';
  }
}
