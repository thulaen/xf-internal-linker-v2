/**
 * PrometheusTabComponent — standalone component for the Prometheus
 * tab on the Error Log page.
 *
 * Shows a small live-metrics card (request rate, p95 latency, error rate,
 * ranking p95, DB connections, queue depth) fetched from the backend's
 * /api/observability/prometheus-summary/ endpoint — which in turn queries
 * VictoriaMetrics. Also provides direct links to VictoriaMetrics (port 8428)
 * and Grafana (port 3000).
 *
 * When VictoriaMetrics is down, each metric card shows an honest
 * "Metrics store unavailable" message rather than a blank that implies
 * all-clear. This satisfies the truthful-state rule from CLAUDE.md.
 */

import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HttpClient } from '@angular/common/http';
import { timer } from 'rxjs';
import { switchMap, catchError } from 'rxjs/operators';
import { EMPTY } from 'rxjs';
import { environment } from '../../../environments/environment';

/** One metric entry as returned by PrometheusSummaryView. */
export interface MetricEntry {
  value: number | null;
  unit: string;
  description: string;
  state: 'ok' | 'no_data' | 'unavailable' | 'parse_error';
  raw?: string;
}

/** Full summary response shape. */
export interface PrometheusSummary {
  request_rate_per_sec: MetricEntry;
  latency_p95_seconds: MetricEntry;
  error_rate_per_sec: MetricEntry;
  ranking_latency_p95_seconds: MetricEntry;
  db_connections: MetricEntry;
  embedding_queue_depth: MetricEntry;
}

interface DisplayCard {
  key: keyof PrometheusSummary;
  label: string;
  icon: string;
  /** Plain-English explanation shown as matTooltip. */
  peHelper: string;
  formatValue: (v: number) => string;
}

const POLL_MS = 30_000;

const CARDS: DisplayCard[] = [
  {
    key: 'request_rate_per_sec',
    label: 'Request Rate',
    icon: 'speed',
    peHelper: 'HTTP requests per second across all Django modules, averaged over the last 5 minutes.',
    formatValue: (v) => `${v.toFixed(2)} req/s`,
  },
  {
    key: 'latency_p95_seconds',
    label: 'API Latency p95',
    icon: 'timer',
    peHelper: '95th-percentile API response time. 95 out of every 100 requests finish faster than this number.',
    formatValue: (v) => `${(v * 1000).toFixed(0)} ms`,
  },
  {
    key: 'error_rate_per_sec',
    label: 'Error Rate',
    icon: 'error_outline',
    peHelper: 'HTTP 5xx (server error) responses per second over the last 5 minutes.',
    formatValue: (v) => `${v.toFixed(3)} err/s`,
  },
  {
    key: 'ranking_latency_p95_seconds',
    label: 'Ranking Latency p95',
    icon: 'psychology',
    peHelper: '95th-percentile time for the Rust ranking engine to score one batch of link candidates.',
    formatValue: (v) => `${v.toFixed(2)} s`,
  },
  {
    key: 'db_connections',
    label: 'DB Connections',
    icon: 'storage',
    peHelper: 'Active Postgres connections right now. Alert fires when this approaches 80 (near the max of 100).',
    formatValue: (v) => `${Math.round(v)}`,
  },
  {
    key: 'embedding_queue_depth',
    label: 'Embedding Queue',
    icon: 'queue',
    peHelper: 'Number of content items waiting to have their embeddings computed. Alert fires above 500.',
    formatValue: (v) => `${Math.round(v)} items`,
  },
];

@Component({
  selector: 'app-prometheus-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './prometheus-tab.component.html',
  styleUrl: './prometheus-tab.component.scss',
})
export class PrometheusTabComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);

  readonly cards = CARDS;
  readonly victoriametricsUrl = 'http://localhost:8428';
  readonly grafanaUrl = 'http://localhost:3000/d/xf-app-health';

  summary: PrometheusSummary | null = null;
  loading = true;
  lastUpdatedAt: string | null = null;

  /** True when every metric is in 'unavailable' state. */
  get storeUnavailable(): boolean {
    if (!this.summary) return false;
    return Object.values(this.summary).every(
      (m: MetricEntry) => m.state === 'unavailable',
    );
  }

  ngOnInit(): void {
    // Poll immediately then every 30 seconds so live values stay fresh
    // while the operator has this tab open.
    timer(0, POLL_MS)
      .pipe(
        switchMap(() =>
          this.http
            .get<PrometheusSummary>(
              `${environment.apiBaseUrl}/observability/prometheus-summary/`,
            )
            .pipe(
              catchError((err) => {
                console.warn('prometheus-summary fetch failed', err);
                return EMPTY;
              }),
            ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (data) => {
          this.summary = data;
          this.loading = false;
          this.lastUpdatedAt = new Date().toISOString();
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.warn('prometheus-summary poll errored', err);
          this.loading = false;
          this.cdr.markForCheck();
        },
      });
  }

  openVictoriaMetrics(): void {
    window.open(this.victoriametricsUrl, '_blank', 'noopener,noreferrer');
  }

  openGrafana(): void {
    window.open(this.grafanaUrl, '_blank', 'noopener,noreferrer');
  }

  getEntry(key: keyof PrometheusSummary): MetricEntry | null {
    return this.summary ? this.summary[key] : null;
  }

  formatEntry(card: DisplayCard): string {
    const entry = this.getEntry(card.key);
    if (!entry) return '—';
    if (entry.state !== 'ok' || entry.value === null) {
      return this.stateLabel(entry.state);
    }
    return card.formatValue(entry.value);
  }

  entryStateClass(card: DisplayCard): string {
    const entry = this.getEntry(card.key);
    if (!entry || entry.state === 'ok') return '';
    return 'metric-unavailable';
  }

  private stateLabel(state: string): string {
    switch (state) {
      case 'no_data':
        return 'No data yet';
      case 'unavailable':
        return 'Unavailable';
      case 'parse_error':
        return 'Parse error';
      default:
        return '—';
    }
  }
}
