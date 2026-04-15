import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiagnosticsService, ServiceStatus, SystemConflict, FeatureReadiness, ResourceUsage, NativeModuleStatus } from './diagnostics.service';
import { ServiceCardComponent } from './service-card/service-card.component';
import { ConflictListComponent } from './conflict-list/conflict-list.component';
import { ReadinessMatrixComponent } from './readiness-matrix/readiness-matrix.component';
import { forkJoin, Subject, takeUntil } from 'rxjs';

interface RuntimeLaneCard {
  id: 'broken_link_scan' | 'graph_sync' | 'import' | 'pipeline';
  title: string;
  owner: 'celery' | 'unknown';
  state: 'healthy' | 'degraded' | 'failed';
  statusLine: string;
  explanation: string;
  nextStep: string;
  badges: RuntimeLaneBadge[];
}

interface RuntimeLaneBadge {
  label: string;
  value: string;
  tone: 'good' | 'warn' | 'bad';
}

interface RuntimeExecutionCard {
  id: 'native_scoring' | 'slate_diversity_runtime' | 'embedding_specialist' | 'scheduler_lane';
  title: string;
  runtime: 'cpp' | 'python' | 'mixed' | 'unknown';
  state: 'healthy' | 'degraded' | 'failed';
  statusLine: string;
  explanation: string;
  nextStep: string;
  badges: RuntimeLaneBadge[];
  details: Array<{ label: string; value: string }>;
  moduleStatuses: NativeModuleStatus[];
}

@Component({
  selector: 'app-diagnostics',
  standalone: true,
  imports: [
    CommonModule,
    ServiceCardComponent,
    ConflictListComponent,
    ReadinessMatrixComponent
  ],
  templateUrl: './diagnostics.component.html',
  styleUrls: ['./diagnostics.component.scss']
})
export class DiagnosticsComponent implements OnInit, OnDestroy {
  private diagnosticsService = inject(DiagnosticsService);
  private destroy$ = new Subject<void>();

  services: ServiceStatus[] = [];
  conflicts: SystemConflict[] = [];
  features: FeatureReadiness[] = [];
  resources: ResourceUsage | null = null;
  runtimeLaneCards: RuntimeLaneCard[] = [];
  runtimeExecutionCards: RuntimeExecutionCard[] = [];
  loading = true;
  refreshing = false;

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    forkJoin({
      services: this.diagnosticsService.getServices(),
      conflicts: this.diagnosticsService.getConflicts(),
      features: this.diagnosticsService.getFeatures(),
      resources: this.diagnosticsService.getResources()
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.services = data.services;
        this.conflicts = data.conflicts;
        this.features = data.features;
        this.resources = data.resources;
        this.runtimeLaneCards = this.buildRuntimeLaneCards(data.services);
        this.runtimeExecutionCards = this.buildRuntimeExecutionCards(data.services);
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading diagnostics data', err);
        this.loading = false;
      }
    });
  }

  refreshAll(): void {
    this.refreshing = true;
    forkJoin({
      services: this.diagnosticsService.refreshServices(),
      conflicts: this.diagnosticsService.detectConflicts()
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.loadData();
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Error refreshing diagnostics', err);
        this.refreshing = false;
      }
    });
  }

  onResolveConflict(id: number): void {
    this.diagnosticsService.resolveConflict(id).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.conflicts = this.conflicts.filter(c => c.id !== id);
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  getHealthyCount(): number {
    return this.services.filter(s => s.state === 'healthy').length;
  }

  runtimeLaneTrackBy(_index: number, lane: RuntimeLaneCard): string {
    return lane.id;
  }

  runtimeExecutionTrackBy(_index: number, card: RuntimeExecutionCard): string {
    return card.id;
  }

  get coreServices(): ServiceStatus[] {
    const runtimeSummaryServices = new Set([
      'runtime_lanes',
      'native_scoring',
      'slate_diversity_runtime',
      'embedding_specialist',
      'scheduler_lane',
    ]);
    return this.services.filter(service => !runtimeSummaryServices.has(service.service_name));
  }

  trackServiceName(_index: number, service: ServiceStatus): string {
    return service.service_name;
  }

  private buildRuntimeLaneCards(services: ServiceStatus[]): RuntimeLaneCard[] {
    const runtimeService = services.find(service => service.service_name === 'runtime_lanes');
    const celeryWorkerService = services.find(service => service.service_name === 'celery_worker');

    const metadata = runtimeService?.metadata ?? {};

    return [
      this.buildLaneCard('broken_link_scan', 'Broken Link Scan', metadata.broken_link_scan_owner, celeryWorkerService),
      this.buildLaneCard('graph_sync', 'Graph Sync', metadata.graph_sync_owner, celeryWorkerService),
      this.buildLaneCard('import', 'Import', metadata.import_owner, celeryWorkerService),
      this.buildLaneCard('pipeline', 'Pipeline', metadata.pipeline_owner, celeryWorkerService),
    ];
  }

  private buildLaneCard(
    id: RuntimeLaneCard['id'],
    title: string,
    rawOwner: unknown,
    celeryWorkerService?: ServiceStatus,
  ): RuntimeLaneCard {
    const owner = rawOwner === 'celery' ? 'celery' : 'unknown';

    if (owner === 'celery') {
      const workerHealthy = celeryWorkerService?.state === 'healthy';
      return {
        id,
        title,
        owner,
        state: workerHealthy ? 'healthy' : celeryWorkerService?.state === 'failed' ? 'failed' : 'degraded',
        statusLine: workerHealthy ? 'Celery owns this lane and the worker is healthy.' : 'Celery owns this lane but the worker needs attention.',
        explanation: 'This heavy path is handled by the native Python/C++ runtime.',
        nextStep: workerHealthy ? 'No action needed.' : (celeryWorkerService?.next_action_step || 'Check the Celery worker health.'),
        badges: this.buildBadges(owner, workerHealthy),
      };
    }

    return {
      id,
      title,
      owner,
      state: 'failed',
      statusLine: 'The active owner for this lane is unknown.',
      explanation: 'Diagnostics did not return a trustworthy runtime owner for this path.',
      nextStep: 'Refresh diagnostics and check the backend runtime-lane snapshot.',
      badges: this.buildBadges(owner, false),
    };
  }

  private buildBadges(
    owner: RuntimeLaneCard['owner'],
    workerAlive: boolean,
  ): RuntimeLaneBadge[] {
    return [
      {
        label: 'Worker Alive',
        value: workerAlive ? 'Yes' : 'No',
        tone: workerAlive ? 'good' : 'bad',
      },
      {
        label: 'Owner',
        value: owner === 'unknown' ? 'Unknown' : owner.toUpperCase(),
        tone: owner === 'celery' ? 'good' : 'bad',
      },
    ];
  }

  private buildRuntimeExecutionCards(services: ServiceStatus[]): RuntimeExecutionCard[] {
    const byName = new Map(services.map(service => [service.service_name, service]));
    const cards: RuntimeExecutionCard[] = [];

    const nativeScoring = byName.get('native_scoring');
    if (nativeScoring) {
      const moduleStatuses = Array.isArray(nativeScoring.metadata?.module_statuses)
        ? nativeScoring.metadata.module_statuses
        : [];
      cards.push({
        id: 'native_scoring',
        title: 'C++ Hot Path',
        runtime: this.asRuntime(nativeScoring.metadata?.runtime_path),
        state: this.asCardState(nativeScoring.state),
        statusLine: nativeScoring.explanation,
        explanation: nativeScoring.metadata?.fallback_reason
          ? `Fallback reason: ${nativeScoring.metadata.fallback_reason}`
          : 'This summarizes the native C++ kernels used for scoring, search, parsing, and reranking.',
        nextStep: nativeScoring.next_action_step,
        badges: [
          this.booleanBadge('Compiled', nativeScoring.metadata?.compiled, true),
          this.booleanBadge('Importable', nativeScoring.metadata?.importable, true),
          this.booleanBadge('Safe To Use', nativeScoring.metadata?.safe_to_use, true),
          this.booleanBadge('Fallback Active', nativeScoring.metadata?.fallback_active, false),
        ],
        details: [
          this.detail('Runtime', this.displayRuntime(nativeScoring.metadata.runtime_path)),
          this.detail('Healthy Modules', this.displayCount(nativeScoring.metadata.healthy_module_count)),
          this.detail('Degraded Modules', this.displayCount(nativeScoring.metadata.degraded_module_count)),
          this.detail('Benchmark', this.displayBenchmark(nativeScoring.metadata.benchmark_status, nativeScoring.metadata.speedup_vs_python)),
          this.detail('C++ Time', this.displayMilliseconds(nativeScoring.metadata.last_benchmark_ms)),
          this.detail('Python Time', this.displayMilliseconds(nativeScoring.metadata.python_benchmark_ms)),
        ],
        moduleStatuses,
      });
    }

    const slateRuntime = byName.get('slate_diversity_runtime');
    if (slateRuntime) {
      cards.push(this.buildSimpleExecutionCard(
        'slate_diversity_runtime',
        'C++ Slate Diversity',
        slateRuntime,
        [
          this.booleanBadge('C++ Active', slateRuntime.metadata.cpp_fast_path_active, true),
          this.booleanBadge('Fallback Active', slateRuntime.metadata.fallback_active, false),
          this.booleanBadge('Safe To Use', slateRuntime.metadata.safe_to_use, true),
        ],
      ));
    }

    const embeddingSpecialist = byName.get('embedding_specialist');
    if (embeddingSpecialist) {
      cards.push(this.buildSimpleExecutionCard(
        'embedding_specialist',
        'Python Specialist Lane',
        embeddingSpecialist,
        [
          this.booleanBadge('Python Active', embeddingSpecialist.metadata?.runtime_path === 'python', true),
          this.booleanBadge('Fallback Active', embeddingSpecialist.metadata?.fallback_active, false),
          this.booleanBadge('Safe To Use', embeddingSpecialist.metadata?.safe_to_use, true),
        ],
      ));
    }

    const schedulerLane = byName.get('scheduler_lane');
    if (schedulerLane) {
      cards.push(this.buildSimpleExecutionCard(
        'scheduler_lane',
        'Task Scheduler',
        schedulerLane,
        [
          this.booleanBadge('Fallback Active', schedulerLane.metadata?.fallback_active, false),
          this.booleanBadge('Safe To Use', schedulerLane.metadata?.safe_to_use, true),
          {
            label: 'Mode',
            value: String(schedulerLane.metadata.scheduler_mode || 'Unknown'),
            tone: schedulerLane.metadata.scheduler_mode === 'active'
              ? 'good'
              : schedulerLane.metadata.scheduler_mode === 'shadow'
                ? 'warn'
                : 'bad',
          },
        ],
      ));
    }

    return cards;
  }

  private buildSimpleExecutionCard(
    id: RuntimeExecutionCard['id'],
    title: string,
    service: ServiceStatus,
    badges: RuntimeLaneBadge[],
  ): RuntimeExecutionCard {
    return {
      id,
      title,
      runtime: this.asRuntime(service.metadata?.runtime_path),
      state: this.asCardState(service.state),
      statusLine: service.explanation,
      explanation: String(service.metadata?.fallback_reason || 'This runtime is tracked through the existing diagnostics system.'),
      nextStep: service.next_action_step,
      badges,
      details: [
        this.detail('Runtime', this.displayRuntime(service.metadata?.runtime_path)),
        this.detail('Owner', String(service.metadata?.owner_selected || 'Tracked by service health')),
        this.detail('Last Error', String(service.metadata?.last_error_summary || 'None reported')),
      ],
      moduleStatuses: [],
    };
  }

  private asRuntime(value: unknown): RuntimeExecutionCard['runtime'] {
    return value === 'cpp' || value === 'python' || value === 'mixed' ? value : 'unknown';
  }

  private asCardState(value: string): RuntimeExecutionCard['state'] {
    return value === 'healthy' || value === 'degraded' || value === 'failed' ? value : 'degraded';
  }

  private booleanBadge(label: string, value: boolean | undefined, truthyGood: boolean): RuntimeLaneBadge {
    const boolValue = !!value;
    const good = truthyGood ? boolValue : !boolValue;
    return {
      label,
      value: boolValue ? 'Yes' : 'No',
      tone: good ? 'good' : 'bad',
    };
  }

  private detail(label: string, value: string): { label: string; value: string } {
    return { label, value };
  }

  private displayRuntime(value: unknown): string {
    const runtime = this.asRuntime(value);
    return runtime === 'unknown' ? 'Unknown' : runtime.toUpperCase();
  }

  private displayCount(value: unknown): string {
    return typeof value === 'number' ? String(value) : 'Unknown';
  }

  private displayBenchmark(status: unknown, speedup: unknown): string {
    if (typeof speedup === 'number') {
      return `${speedup.toFixed(2)}x vs Python`;
    }
    return String(status || 'Not captured yet').replace(/_/g, ' ');
  }

  private displayMilliseconds(value: unknown): string {
    return typeof value === 'number' ? `${value.toFixed(2)} ms` : 'Not captured yet';
  }

  trackByIndex(index: number): number { return index; }
  trackByLabel(_: number, item: { label: string }): string { return item.label; }
}
