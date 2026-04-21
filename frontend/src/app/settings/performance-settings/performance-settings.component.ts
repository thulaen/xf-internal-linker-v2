import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, EMPTY, finalize } from 'rxjs';

import {
  HelperNodeSettingsRecord,
  RuntimeAuditEntry,
  RuntimeModelPlacement,
  RuntimeModelRegistryEntry,
  RuntimeSummaryPayload,
  SiloSettingsService,
} from '../silo-settings.service';

interface RuntimeRegistrationForm {
  model_name: string;
  model_family: string;
  dimension: number;
  device_target: string;
  batch_size: number;
  role: string;
  executor_type: string;
  helper_id: number | null;
}

@Component({
  selector: 'app-performance-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSliderModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './performance-settings.component.html',
  styleUrls: ['./performance-settings.component.scss'],
})
export class PerformanceSettingsComponent implements OnInit {
  private siloSettings = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  readonly batchSize = signal<number>(32);
  readonly gpuMemoryBudget = signal<number>(60);
  readonly gpuTempPause = signal<number>(90);
  readonly cpuEncodeThreads = signal<number>(4);
  readonly defaultQueueConcurrency = signal<number>(2);
  readonly aggressiveOomBackoff = signal<boolean>(true);
  readonly batchMin = signal<number>(8);
  readonly batchMax = signal<number>(128);
  readonly gpuBudgetMin = signal<number>(25);
  readonly gpuBudgetMax = signal<number>(80);
  readonly gpuTempMin = signal<number>(75);
  readonly gpuTempMax = signal<number>(95);
  readonly cpuThreadsMin = signal<number>(1);
  readonly cpuThreadsMax = signal<number>(10);
  readonly queueConcMin = signal<number>(1);
  readonly queueConcMax = signal<number>(6);
  readonly saving = signal<boolean>(false);
  readonly runtimeLoading = signal<boolean>(true);
  readonly registering = signal<boolean>(false);
  readonly actionPending = signal<boolean>(false);
  readonly deletingPlacement = signal<boolean>(false);
  readonly runtimeSummary = signal<RuntimeSummaryPayload | null>(null);
  readonly helpers = signal<HelperNodeSettingsRecord[]>([]);

  registration: RuntimeRegistrationForm = {
    model_name: '',
    model_family: 'sentence-transformers',
    dimension: 1024,
    device_target: 'cpu',
    batch_size: 32,
    role: 'candidate',
    executor_type: 'primary',
    helper_id: null,
  };

  private initialBatch = 32;
  private initialGpuMemoryBudget = 60;
  private initialGpuTempPause = 90;
  private initialCpuEncodeThreads = 4;
  private initialDefaultQueueConcurrency = 2;
  private initialAggressiveOomBackoff = true;

  readonly dirtyConcurrency = computed(
    () => this.defaultQueueConcurrency() !== this.initialDefaultQueueConcurrency,
  );

  ngOnInit(): void {
    this.loadRuntimeConfig();
    this.reloadRuntime();
  }

  private loadRuntimeConfig(): void {
    this.siloSettings.getRuntimeConfig()
      .pipe(catchError(() => EMPTY), takeUntilDestroyed(this.destroyRef))
      .subscribe((cfg) => {
        if (!cfg) return;
        this.batchSize.set(cfg.embedding_batch_size);
        this.gpuMemoryBudget.set(cfg.gpu_memory_budget_pct);
        this.gpuTempPause.set(cfg.gpu_temp_pause_c);
        this.cpuEncodeThreads.set(cfg.cpu_encode_threads);
        this.defaultQueueConcurrency.set(cfg.default_queue_concurrency);
        this.aggressiveOomBackoff.set(cfg.aggressive_oom_backoff);
        this.initialBatch = cfg.embedding_batch_size;
        this.initialGpuMemoryBudget = cfg.gpu_memory_budget_pct;
        this.initialGpuTempPause = cfg.gpu_temp_pause_c;
        this.initialCpuEncodeThreads = cfg.cpu_encode_threads;
        this.initialDefaultQueueConcurrency = cfg.default_queue_concurrency;
        this.initialAggressiveOomBackoff = cfg.aggressive_oom_backoff;
        this.batchMin.set(cfg.embedding_batch_size_range[0]);
        this.batchMax.set(cfg.embedding_batch_size_range[1]);
        this.gpuBudgetMin.set(cfg.gpu_memory_budget_pct_range[0]);
        this.gpuBudgetMax.set(cfg.gpu_memory_budget_pct_range[1]);
        this.gpuTempMin.set(cfg.gpu_temp_pause_c_range[0]);
        this.gpuTempMax.set(cfg.gpu_temp_pause_c_range[1]);
        this.cpuThreadsMin.set(cfg.cpu_encode_threads_range[0]);
        this.cpuThreadsMax.set(cfg.cpu_encode_threads_range[1]);
        this.queueConcMin.set(cfg.default_queue_concurrency_range[0]);
        this.queueConcMax.set(cfg.default_queue_concurrency_range[1]);
      });
  }

  reloadRuntime(): void {
    this.runtimeLoading.set(true);
    this.siloSettings.getRuntimeSummary()
      .pipe(
        finalize(() => this.runtimeLoading.set(false)),
        catchError(() => {
          this.snack.open('Could not load runtime summary.', 'Dismiss', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((runtime) => {
        this.runtimeSummary.set(runtime);
        const suggestedDevice = runtime.model_runtime.active_model?.device_target
          || (runtime.hardware.gpu_name ? 'cuda' : 'cpu');
        this.registration.device_target = suggestedDevice;
        this.registration.batch_size = runtime.recommended_profile.suggested_batch_size;
      });

    this.siloSettings.listHelpers()
      .pipe(catchError(() => EMPTY), takeUntilDestroyed(this.destroyRef))
      .subscribe((helpers) => this.helpers.set(helpers));
  }

  applyRecommendedProfile(): void {
    const runtime = this.runtimeSummary();
    if (!runtime) return;
    this.batchSize.set(runtime.recommended_profile.suggested_batch_size);
    this.defaultQueueConcurrency.set(runtime.recommended_profile.suggested_concurrency);
    this.snack.open(
      `${runtime.recommended_profile.profile} profile applied to the draft controls below.`,
      'Dismiss',
      { duration: 3500 },
    );
  }

  registerModel(): void {
    if (!this.registration.model_name.trim()) {
      this.snack.open('Model name is required.', 'Dismiss', { duration: 3000 });
      return;
    }
    if (this.registration.executor_type === 'helper' && !this.registration.helper_id) {
      this.snack.open('Choose a helper node for helper placements.', 'Dismiss', { duration: 3000 });
      return;
    }

    this.registering.set(true);
    this.siloSettings.registerRuntimeModel({
      task_type: 'embedding',
      model_name: this.registration.model_name.trim(),
      model_family: this.registration.model_family.trim(),
      dimension: Number(this.registration.dimension),
      device_target: this.registration.device_target,
      batch_size: Number(this.registration.batch_size),
      role: this.registration.role,
      executor_type: this.registration.executor_type,
      helper_id: this.registration.executor_type === 'helper' ? this.registration.helper_id : null,
    })
      .pipe(
        finalize(() => this.registering.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not register model.', 'Dismiss', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.registration.model_name = '';
        this.registration.helper_id = null;
        this.snack.open('Runtime model registered.', 'Dismiss', { duration: 3000 });
        this.reloadRuntime();
      });
  }

  runModelAction(model: RuntimeModelRegistryEntry, action: 'download' | 'warm' | 'pause' | 'resume' | 'promote' | 'rollback' | 'drain'): void {
    this.actionPending.set(true);
    this.siloSettings.runRuntimeModelAction(model.id, { action })
      .pipe(
        finalize(() => this.actionPending.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || `Could not ${action} ${model.model_name}.`, 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.snack.open(`${action} queued for ${model.model_name}.`, 'Dismiss', { duration: 3000 });
        this.reloadRuntime();
      });
  }

  deletePlacement(placement: RuntimeModelPlacement): void {
    this.deletingPlacement.set(true);
    this.siloSettings.deleteRuntimePlacement(placement.id)
      .pipe(
        finalize(() => this.deletingPlacement.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not delete that placement yet.', 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        const reclaimed = result?.reclaimed_disk_bytes ? this.humanBytes(result.reclaimed_disk_bytes) : 'disk space';
        this.snack.open(`Placement deleted. Reclaimed ${reclaimed}.`, 'Dismiss', { duration: 3500 });
        this.reloadRuntime();
      });
  }

  save(): void {
    this.saving.set(true);
    this.siloSettings.updateRuntimeConfig({
      embedding_batch_size: this.batchSize(),
      gpu_memory_budget_pct: this.gpuMemoryBudget(),
      gpu_temp_pause_c: this.gpuTempPause(),
      cpu_encode_threads: this.cpuEncodeThreads(),
      default_queue_concurrency: this.defaultQueueConcurrency(),
      aggressive_oom_backoff: this.aggressiveOomBackoff(),
    })
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
        this.initialGpuMemoryBudget = this.gpuMemoryBudget();
        this.initialGpuTempPause = this.gpuTempPause();
        this.initialCpuEncodeThreads = this.cpuEncodeThreads();
        this.initialDefaultQueueConcurrency = this.defaultQueueConcurrency();
        this.initialAggressiveOomBackoff = this.aggressiveOomBackoff();
        this.snack.open('Performance settings saved.', 'OK', { duration: 2500 });
      });
  }

  reset(): void {
    this.batchSize.set(this.initialBatch);
    this.gpuMemoryBudget.set(this.initialGpuMemoryBudget);
    this.gpuTempPause.set(this.initialGpuTempPause);
    this.cpuEncodeThreads.set(this.initialCpuEncodeThreads);
    this.defaultQueueConcurrency.set(this.initialDefaultQueueConcurrency);
    this.aggressiveOomBackoff.set(this.initialAggressiveOomBackoff);
  }

  humanBytes(bytes: number | null | undefined): string {
    const value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = value;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }

  labelWithMb = (v: number): string => `${v}`;

  trackByHelperId = (_: number, h: HelperNodeSettingsRecord): number => h.id;
  trackByPlacementId = (_: number, p: RuntimeModelPlacement): number => p.id;
  trackByAuditEntryId = (_: number, e: RuntimeAuditEntry): number => e.id;
}
