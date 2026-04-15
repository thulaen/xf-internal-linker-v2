import { Component, OnInit, ChangeDetectionStrategy, DestroyRef, inject, signal, computed } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, of, switchMap, timer } from 'rxjs';

interface GpuMetrics {
  available: boolean;
  temp_c: number | null;
  vram_used_mb: number | null;
  vram_total_mb: number | null;
  vram_percent: number | null;
  utilization_pct: number | null;
}

interface SystemMetrics {
  cpu_percent: number | null;
  ram_used_mb: number | null;
  ram_total_mb: number | null;
  ram_percent: number | null;
  gpu: GpuMetrics;
}

/**
 * Live system metrics tile for the dashboard. Polls every 10 seconds.
 *
 * Purpose: show a non-technical user, at a glance, whether their computer
 * is under pressure. Colour changes from green → amber → red as usage climbs
 * so the user can decide to drop to Safe Mode or close apps.
 *
 * Data source: GET /api/system/metrics/ (combined psutil + pynvml).
 */
@Component({
  selector: 'app-system-metrics',
  standalone: true,
  imports: [DecimalPipe, MatCardModule, MatIconModule, MatProgressBarModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="system-metrics">
      <mat-card-header>
        <mat-icon mat-card-avatar>monitor_heart</mat-icon>
        <mat-card-title>System Load</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="meter-row" [matTooltip]="'Processor usage — how busy your CPU is right now'">
          <div class="meter-head">
            <mat-icon class="meter-icon">memory</mat-icon>
            <span class="meter-label">CPU</span>
            <span class="meter-value" [class]="tintClass(metrics()?.cpu_percent)">
              {{ (metrics()?.cpu_percent ?? null) === null ? '—' : (metrics()!.cpu_percent | number:'1.0-0') + '%' }}
            </span>
          </div>
          <mat-progress-bar
            [value]="metrics()?.cpu_percent ?? 0"
            [color]="barColor(metrics()?.cpu_percent)"
            mode="determinate"
          ></mat-progress-bar>
        </div>

        <div class="meter-row" [matTooltip]="ramTooltip()">
          <div class="meter-head">
            <mat-icon class="meter-icon">memory_alt</mat-icon>
            <span class="meter-label">RAM</span>
            <span class="meter-value" [class]="tintClass(metrics()?.ram_percent)">
              {{ (metrics()?.ram_percent ?? null) === null ? '—' : (metrics()!.ram_percent | number:'1.0-0') + '%' }}
            </span>
          </div>
          <mat-progress-bar
            [value]="metrics()?.ram_percent ?? 0"
            [color]="barColor(metrics()?.ram_percent)"
            mode="determinate"
          ></mat-progress-bar>
          <span class="meter-sub">
            {{ metrics()?.ram_used_mb ?? 0 | number:'1.0-0' }} MB of
            {{ metrics()?.ram_total_mb ?? 0 | number:'1.0-0' }} MB
          </span>
        </div>

        @if (metrics()?.gpu?.available) {
          <div class="meter-row" [matTooltip]="gpuTooltip()">
            <div class="meter-head">
              <mat-icon class="meter-icon">bolt</mat-icon>
              <span class="meter-label">GPU memory (VRAM)</span>
              <span class="meter-value" [class]="tintClass(metrics()?.gpu?.vram_percent)">
                {{ (metrics()?.gpu?.vram_percent ?? null) === null ? '—' : (metrics()!.gpu!.vram_percent! | number:'1.0-0') + '%' }}
              </span>
            </div>
            <mat-progress-bar
              [value]="metrics()?.gpu?.vram_percent ?? 0"
              [color]="barColor(metrics()?.gpu?.vram_percent)"
              mode="determinate"
            ></mat-progress-bar>
            <span class="meter-sub">
              {{ metrics()?.gpu?.vram_used_mb ?? 0 | number:'1.0-0' }} MB of
              {{ metrics()?.gpu?.vram_total_mb ?? 0 | number:'1.0-0' }} MB
              · GPU temp
              <strong [class.temp-hot]="(metrics()?.gpu?.temp_c ?? 0) >= 86">
                {{ (metrics()?.gpu?.temp_c ?? null) === null ? '—' : metrics()!.gpu!.temp_c + '°C' }}
              </strong>
              @if ((metrics()?.gpu?.temp_c ?? 0) >= 86) {
                <mat-icon class="warn-inline" matTooltip="GPU is at or above the 86°C ceiling — heavy tasks will pause automatically">warning</mat-icon>
              }
            </span>
          </div>
        } @else {
          <div class="gpu-unavailable">
            <mat-icon>info</mat-icon>
            <span>No GPU detected. CPU-only mode is active.</span>
          </div>
        }

        @if (tip()) {
          <div class="suggestion-tip" [matTooltip]="'Advice based on current usage'">
            <mat-icon>lightbulb</mat-icon>
            <span>{{ tip() }}</span>
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .meter-row { margin-bottom: var(--space-md); }
    .meter-row:last-child { margin-bottom: 0; }
    .meter-head {
      display: flex;
      align-items: center;
      gap: var(--space-xs);
      margin-bottom: var(--space-xs);
    }
    .meter-icon { font-size: 16px; width: 16px; height: 16px; color: var(--color-text-muted); }
    .meter-label { font-size: 12px; font-weight: 500; color: var(--color-text-secondary); flex: 1; }
    .meter-value { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
    .meter-value.tint-ok { color: var(--color-success-dark, #137333); }
    .meter-value.tint-warn { color: var(--color-warning, #a77a00); }
    .meter-value.tint-hot { color: var(--color-error, #c5221f); }
    .meter-sub {
      display: block;
      margin-top: var(--space-xs);
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .temp-hot { color: var(--color-error, #c5221f); }
    .warn-inline {
      font-size: 14px; width: 14px; height: 14px;
      color: var(--color-error, #c5221f);
      vertical-align: middle;
      margin-left: 4px;
    }
    .gpu-unavailable {
      display: flex; align-items: center; gap: var(--space-xs);
      padding: var(--space-sm);
      border-radius: var(--radius-md, 8px);
      background: var(--color-bg-faint);
      font-size: 12px;
      color: var(--color-text-muted);
    }
    .gpu-unavailable mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .suggestion-tip {
      margin-top: var(--space-md);
      display: flex; align-items: flex-start; gap: var(--space-xs);
      padding: var(--space-sm);
      border-radius: var(--radius-md, 8px);
      background: var(--color-blue-50, #e8f0fe);
      color: var(--color-primary);
      font-size: 12px;
    }
    .suggestion-tip mat-icon { font-size: 16px; width: 16px; height: 16px; margin-top: 1px; }
  `],
})
export class SystemMetricsComponent implements OnInit {
  private http = inject(HttpClient);
  private destroyRef = inject(DestroyRef);

  readonly metrics = signal<SystemMetrics | null>(null);

  readonly ramTooltip = computed(() => {
    const m = this.metrics();
    if (!m || m.ram_used_mb === null || m.ram_used_mb === undefined) return 'Main memory usage';
    return `Main memory: ${m.ram_used_mb} MB of ${m.ram_total_mb} MB in use`;
  });

  readonly gpuTooltip = computed(() => {
    const g = this.metrics()?.gpu;
    if (!g || !g.available) return 'No GPU detected';
    return `GPU memory: ${g.vram_used_mb} MB of ${g.vram_total_mb} MB in use · temperature ${g.temp_c}°C`;
  });

  readonly tip = computed(() => {
    const m = this.metrics();
    if (!m) return '';
    if ((m.gpu?.temp_c ?? 0) >= 86) {
      return 'GPU is very hot. Heavy tasks will pause until it cools down. Switch to Safe Mode if you need the GPU for something else.';
    }
    if ((m.ram_percent ?? 0) >= 90) {
      return 'Memory is almost full. Close some Chrome tabs or switch to Safe Mode.';
    }
    if ((m.gpu?.vram_percent ?? 0) >= 80) {
      return 'GPU memory is running low. Consider Safe Mode to free some up for other apps.';
    }
    if ((m.cpu_percent ?? 0) >= 85) {
      return 'CPU is near full. Background work is happening now — results should be fast.';
    }
    return '';
  });

  ngOnInit(): void {
    // Poll every 10 seconds. First sample fires immediately.
    timer(0, 10_000)
      .pipe(
        switchMap(() =>
          this.http.get<SystemMetrics>('/api/system/metrics/').pipe(
            catchError(() => of(null)),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((data) => {
        if (data) {
          this.metrics.set(data);
        }
      });
  }

  tintClass(pct: number | null | undefined): string {
    if (pct === null || pct === undefined) return '';
    if (pct >= 85) return 'tint-hot';
    if (pct >= 65) return 'tint-warn';
    return 'tint-ok';
  }

  barColor(pct: number | null | undefined): 'primary' | 'accent' | 'warn' {
    if (pct === null || pct === undefined) return 'primary';
    if (pct >= 85) return 'warn';
    if (pct >= 65) return 'accent';
    return 'primary';
  }
}
