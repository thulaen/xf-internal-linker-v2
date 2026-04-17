import { Component, DestroyRef, OnInit, ChangeDetectionStrategy, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSliderModule } from '@angular/material/slider';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { catchError, EMPTY } from 'rxjs';

interface RuntimeConfig {
  embedding_batch_size: number;
  celery_concurrency: number;
  embedding_batch_size_range: [number, number];
  celery_concurrency_range: [number, number];
  celery_concurrency_requires_restart: boolean;
}

/**
 * Noob-friendly runtime tunables.
 *   - Batch size: applies to the next pipeline run (no restart).
 *   - Worker count: applies after Docker restart (clearly labelled).
 */
@Component({
  selector: 'app-performance-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatSliderModule,
    MatSnackBarModule,
    MatTooltipModule,
    MatDividerModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="perf-settings">
      <mat-card class="setting-card">
        <mat-card-header>
          <mat-icon mat-card-avatar>layers</mat-icon>
          <mat-card-title>Batch size</mat-card-title>
          <mat-card-subtitle>How many paragraphs the linker processes at once.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="plain-text">
            Bigger batch = faster runs, but uses more memory. If the linker ever runs out of memory,
            drop this number. The default (32) is safe on most machines.
          </p>
          <div class="slider-row">
            <mat-slider
              [min]="batchMin()"
              [max]="batchMax()"
              [step]="8"
              discrete
              [displayWith]="labelWithMb">
              <input matSliderThumb
                     [ngModel]="batchSize()"
                     (ngModelChange)="batchSize.set($event)" />
            </mat-slider>
            <span class="slider-value">{{ batchSize() }}</span>
          </div>
          <div class="slider-ends">
            <span>{{ batchMin() }}</span>
            <span>{{ batchMax() }}</span>
          </div>
        </mat-card-content>
      </mat-card>

      <mat-card class="setting-card">
        <mat-card-header>
          <mat-icon mat-card-avatar>group_work</mat-icon>
          <mat-card-title>Worker count</mat-card-title>
          <mat-card-subtitle>Background helpers that run jobs in parallel.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="plain-text">
            More workers = more things in parallel, but each one uses memory. The default (2) is safe.
            <strong>Takes effect after the next Docker restart</strong> — this is a deliberate safety
            step, not a bug.
          </p>
          <div class="slider-row">
            <mat-slider
              [min]="concMin()"
              [max]="concMax()"
              [step]="1"
              discrete>
              <input matSliderThumb
                     [ngModel]="concurrency()"
                     (ngModelChange)="concurrency.set($event)" />
            </mat-slider>
            <span class="slider-value">{{ concurrency() }}</span>
          </div>
          <div class="slider-ends">
            <span>{{ concMin() }}</span>
            <span>{{ concMax() }}</span>
          </div>
          @if (dirtyConcurrency()) {
            <div class="restart-banner" role="alert">
              <mat-icon>restart_alt</mat-icon>
              <span>
                Worker count changed. The new setting applies <strong>after a Docker restart</strong>
                (run <code>docker-compose restart celery-worker</code>).
              </span>
            </div>
          }
        </mat-card-content>
      </mat-card>

      <div class="actions">
        <button mat-stroked-button type="button" (click)="reset()" [disabled]="saving()">
          <mat-icon>refresh</mat-icon> Reset to defaults
        </button>
        <button mat-flat-button color="primary" type="button" (click)="save()" [disabled]="saving()">
          <mat-icon>{{ saving() ? 'sync' : 'save' }}</mat-icon>
          {{ saving() ? 'Saving…' : 'Save changes' }}
        </button>
      </div>
    </div>
  `,
  styles: [`
    .perf-settings { display: flex; flex-direction: column; gap: var(--space-md); padding: var(--space-md); }
    .setting-card { padding: var(--spacing-card); }
    .plain-text { font-size: 13px; color: var(--color-text-secondary); line-height: 1.5; margin: 0 0 var(--space-sm) 0; }
    .slider-row { display: flex; align-items: center; gap: var(--space-sm); }
    .slider-row mat-slider { flex: 1; }
    .slider-value {
      font-size: 14px;
      font-weight: 600;
      min-width: 36px;
      text-align: right;
      font-variant-numeric: tabular-nums;
      color: var(--color-primary);
    }
    .slider-ends {
      display: flex;
      justify-content: space-between;
      margin-top: 4px;
      font-size: 11px;
      color: var(--color-text-muted);
      padding: 0 8px;
    }
    .restart-banner {
      margin-top: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      background: var(--color-warning-light, #fef7e0);
      border-left: 3px solid var(--color-warning, #a77a00);
      border-radius: var(--radius-sm, 4px);
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-size: 12px;
      color: var(--color-warning-dark, #5e4100);
    }
    .restart-banner mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .restart-banner code {
      background: rgba(0,0,0,0.08);
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 11px;
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-sm);
    }
  `],
})
export class PerformanceSettingsComponent implements OnInit {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);

  readonly batchSize = signal<number>(32);
  readonly concurrency = signal<number>(2);
  readonly batchMin = signal<number>(8);
  readonly batchMax = signal<number>(128);
  readonly concMin = signal<number>(1);
  readonly concMax = signal<number>(8);
  readonly saving = signal<boolean>(false);

  private initialBatch = 32;
  private initialConcurrency = 2;

  readonly dirtyConcurrency = () => this.concurrency() !== this.initialConcurrency;

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.http.get<RuntimeConfig>('/api/settings/runtime-config/')
      .pipe(catchError(() => EMPTY), takeUntilDestroyed(this.destroyRef))
      .subscribe((cfg) => {
        if (!cfg) return;
        this.batchSize.set(cfg.embedding_batch_size);
        this.concurrency.set(cfg.celery_concurrency);
        this.initialBatch = cfg.embedding_batch_size;
        this.initialConcurrency = cfg.celery_concurrency;
        this.batchMin.set(cfg.embedding_batch_size_range[0]);
        this.batchMax.set(cfg.embedding_batch_size_range[1]);
        this.concMin.set(cfg.celery_concurrency_range[0]);
        this.concMax.set(cfg.celery_concurrency_range[1]);
      });
  }

  save(): void {
    this.saving.set(true);
    this.http.post<{ updated: Record<string, number>; errors?: unknown }>(
      '/api/settings/runtime-config/',
      {
        embedding_batch_size: this.batchSize(),
        celery_concurrency: this.concurrency(),
      },
    )
      .pipe(
        catchError(() => {
          this.saving.set(false);
          this.snack.open('Could not save. Try again.', 'OK', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.saving.set(false);
        this.initialBatch = this.batchSize();
        this.initialConcurrency = this.concurrency();
        this.snack.open('Performance settings saved.', 'OK', { duration: 2500 });
      });
  }

  reset(): void {
    this.batchSize.set(32);
    this.concurrency.set(2);
  }

  labelWithMb = (v: number): string => `${v}`;
}
