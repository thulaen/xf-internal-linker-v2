import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiagnosticsService, ServiceStatus, SystemConflict, FeatureReadiness, ResourceUsage } from './diagnostics.service';
import { ServiceCardComponent } from './service-card/service-card.component';
import { ConflictListComponent } from './conflict-list/conflict-list.component';
import { ReadinessMatrixComponent } from './readiness-matrix/readiness-matrix.component';
import { forkJoin, Subject, takeUntil } from 'rxjs';

interface RuntimeLaneCard {
  id: 'broken_link_scan' | 'graph_sync' | 'import' | 'pipeline';
  title: string;
  owner: 'csharp' | 'celery' | 'unknown';
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

  private buildRuntimeLaneCards(services: ServiceStatus[]): RuntimeLaneCard[] {
    const runtimeService = services.find(service => service.service_name === 'runtime_lanes');
    const httpWorkerService = services.find(service => service.service_name === 'http_worker');
    const celeryWorkerService = services.find(service => service.service_name === 'celery_worker');

    const metadata = runtimeService?.metadata ?? {};

    return [
      this.buildLaneCard(
        'broken_link_scan',
        'Broken Link Scan',
        metadata['broken_link_scan_owner'],
        httpWorkerService,
        celeryWorkerService
      ),
      this.buildLaneCard(
        'graph_sync',
        'Graph Sync',
        metadata['graph_sync_owner'],
        httpWorkerService,
        celeryWorkerService
      ),
      this.buildLaneCard(
        'import',
        'Import',
        metadata['import_owner'],
        httpWorkerService,
        celeryWorkerService
      ),
      this.buildLaneCard(
        'pipeline',
        'Pipeline',
        metadata['pipeline_owner'],
        httpWorkerService,
        celeryWorkerService
      ),
    ];
  }

  private buildLaneCard(
    id: RuntimeLaneCard['id'],
    title: string,
    rawOwner: unknown,
    httpWorkerService?: ServiceStatus,
    celeryWorkerService?: ServiceStatus,
  ): RuntimeLaneCard {
    const owner = rawOwner === 'csharp' || rawOwner === 'celery' ? rawOwner : 'unknown';

    if (owner === 'csharp') {
      if (httpWorkerService?.state === 'healthy') {
        return {
          id,
          title,
          owner,
          state: 'healthy',
          statusLine: 'C# owns this lane and the worker lane is healthy.',
          explanation: 'This heavy path is routed to the C# runtime right now.',
          nextStep: 'No action needed unless job results look wrong.',
          badges: this.buildBadges(owner, true, false),
        };
      }

      if (httpWorkerService?.state === 'failed') {
        return {
          id,
          title,
          owner,
          state: 'failed',
          statusLine: 'C# is selected, but the worker lane is down.',
          explanation: 'The cutover setting points at C#, but the runtime cannot be trusted yet.',
          nextStep: httpWorkerService.next_action_step || 'Restore the C# worker lane before trusting this path.',
          badges: this.buildBadges(owner, false, true),
        };
      }

      return {
        id,
        title,
        owner,
        state: 'degraded',
        statusLine: 'C# is selected, but the worker lane is degraded.',
        explanation: 'This lane is cut over, but the C# runtime still needs attention.',
        nextStep: httpWorkerService?.next_action_step || 'Check the C# runtime health details below.',
        badges: this.buildBadges(owner, false, true),
      };
    }

    if (owner === 'celery') {
      return {
        id,
        title,
        owner,
        state: celeryWorkerService?.state === 'failed' ? 'failed' : 'degraded',
        statusLine: 'Celery still owns this lane.',
        explanation: 'This path has not moved to C# yet, so the heavy runtime migration is not finished here.',
        nextStep: 'Move this lane to C# and leave Celery only as rollback until parity is proven.',
        badges: this.buildBadges(owner, celeryWorkerService?.state === 'healthy', true),
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
      badges: this.buildBadges(owner, false, true),
    };
  }

  private buildBadges(
    owner: RuntimeLaneCard['owner'],
    workerAlive: boolean,
    cutoverIncomplete: boolean,
  ): RuntimeLaneBadge[] {
    return [
      {
        label: 'Worker Alive',
        value: workerAlive ? 'Yes' : 'No',
        tone: workerAlive ? 'good' : 'bad',
      },
      {
        label: 'Owner Selected',
        value: owner === 'unknown' ? 'Unknown' : owner.toUpperCase(),
        tone: owner === 'csharp' ? 'good' : owner === 'celery' ? 'warn' : 'bad',
      },
      {
        label: 'Cutover Incomplete',
        value: cutoverIncomplete ? 'Yes' : 'No',
        tone: cutoverIncomplete ? 'warn' : 'good',
      },
    ];
  }
}
