import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute } from '@angular/router';
import { forkJoin, of, Subject, timer } from 'rxjs';
import { catchError, switchMap, takeUntil } from 'rxjs/operators';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { PersistTabDirective } from '../core/directives/persist-tab.directive';
import { GlitchtipService } from '../core/services/glitchtip.service';
import { RealtimeService } from '../core/services/realtime.service';
import { ScrollAttentionService } from '../core/services/scroll-attention.service';
import { TopicUpdate } from '../core/services/realtime.types';
import { environment } from '../../environments/environment';
import { buildAIPromptForError, diffErrorSnapshot, ErrorGroup, groupErrors, maxTrendCount as maxTrendCountFn, relatedErrors as relatedErrorsFn, trackErrorId as trackErrorIdFn, trackGroupFingerprint as trackGroupFingerprintFn, trackNodeId as trackNodeIdFn, trackTrendDate as trackTrendDateFn, trendLabel as trendLabelFn, uniqueNodeIds } from './diagnostics.error-log';
import { DiagnosticsService, ErrorLogEntry, FeatureReadiness, NdcgEvalResult, NodeSummary, PipelineGate, ResourceUsage, RuntimeContext, ServiceStatus, SystemConflict } from './diagnostics.service';
import { dispatchRealtimeUpdate, removeConflictFrom, removeServiceFrom, upsertConflictInto, upsertServiceInto } from './diagnostics.realtime';
import { buildRuntimeExecutionCards, buildRuntimeLaneCards, RuntimeExecutionCard, RuntimeLaneCard } from './diagnostics.runtime-cards';
import { ConflictListComponent } from './conflict-list/conflict-list.component';
import { ReadinessMatrixComponent } from './readiness-matrix/readiness-matrix.component';
import { ServiceCardComponent } from './service-card/service-card.component';
import { SuppressedPairsCardComponent } from './suppressed-pairs-card/suppressed-pairs-card.component';

const RUNTIME_SUMMARY_SERVICES = new Set([
  'runtime_lanes', 'native_scoring', 'slate_diversity_runtime', 'embedding_specialist', 'scheduler_lane',
]);
const GLITCHTIP_TAB_INDEX = 1;
const ERROR_TAB_FRAGMENT_TO_INDEX: Record<string, number> = {
  'internal-errors-tab': 0, 'glitchtip-errors-tab': 1, 'all-errors-tab': 2,
};

@Component({
  selector: 'app-diagnostics',
  standalone: true,
  imports: [
    CommonModule, MatTooltipModule, MatButtonModule, MatIconModule, MatTabsModule,
    PersistTabDirective, ServiceCardComponent, ConflictListComponent,
    ReadinessMatrixComponent, SuppressedPairsCardComponent,
  ],
  templateUrl: './diagnostics.component.html',
  styleUrls: ['./diagnostics.component.scss'],
})
export class DiagnosticsComponent implements OnInit, OnDestroy {
  private readonly diagnosticsService = inject(DiagnosticsService);
  private readonly glitchtipService = inject(GlitchtipService);
  private readonly realtime = inject(RealtimeService);
  private readonly route = inject(ActivatedRoute);
  private readonly scrollAttention = inject(ScrollAttentionService);
  private readonly snack = inject(MatSnackBar);
  private readonly visibilityGate = inject(VisibilityGateService);
  private readonly destroy$ = new Subject<void>();

  services: ServiceStatus[] = [];
  conflicts: SystemConflict[] = [];
  features: FeatureReadiness[] = [];
  resources: ResourceUsage | null = null;
  /** Polish.B — populated daily by the ndcg_smoke_test scheduled job. */
  ndcgEval: NdcgEvalResult | null = null;
  runtimeLaneCards: RuntimeLaneCard[] = [];
  runtimeExecutionCards: RuntimeExecutionCard[] = [];
  loading = true;
  refreshing = false;
  errors: ErrorLogEntry[] = [];
  acknowledgedErrors: ErrorLogEntry[] = [];
  runtimeCtx: RuntimeContext | null = null;
  glitchtipEvents: ErrorLogEntry[] = [];
  glitchtipLastSyncedAt: string | null = null;
  selectedErrorTabIndex = 0;
  nodes: NodeSummary[] = [];
  pipelineGate: PipelineGate | null = null;
  expandedErrorId: number | null = null;
  filterNodeId: string | null = null;
  copyFeedbackId: number | null = null;
  readonly adminUrl = environment.adminUrl;
  readonly glitchtipBaseUrl = environment.glitchtipBaseUrl;

  ngOnInit(): void {
    this.route.fragment.pipe(takeUntil(this.destroy$)).subscribe((fragment) => {
      if (!fragment || !(fragment in ERROR_TAB_FRAGMENT_TO_INDEX)) return;
      this.selectedErrorTabIndex = ERROR_TAB_FRAGMENT_TO_INDEX[fragment];
      if (this.selectedErrorTabIndex === GLITCHTIP_TAB_INDEX) this.refreshGlitchtipEvents();
    });
    this.loadData();
    this.subscribeToRealtimeUpdates();
    this.startErrorLogPoll();
    this.startGlitchtipPoll();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private startErrorLogPoll(): void {
    // Gated by `VisibilityGateService` — hidden tabs / signed-out
    // sessions skip the poll. See docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(30_000, 30_000).pipe(
          switchMap(() =>
            this.diagnosticsService
              .getErrors()
              .pipe(catchError(() => of<ErrorLogEntry[] | null>(null))),
          ),
        ),
      )
      .pipe(takeUntil(this.destroy$))
      .subscribe((next) => {
        if (next) this.reconcileErrorSnapshot(next);
      });
  }

  private startGlitchtipPoll(): void {
    // Gated by `VisibilityGateService`.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(30_000, 30_000).pipe(
          switchMap(() =>
            this.selectedErrorTabIndex === GLITCHTIP_TAB_INDEX
              ? this.glitchtipService
                  .getRecentEvents()
                  .pipe(catchError(() => of<ErrorLogEntry[] | null>(null)))
              : of<ErrorLogEntry[] | null>(null),
          ),
        ),
      )
      .pipe(takeUntil(this.destroy$))
      .subscribe((next) => {
        if (next) this.applyGlitchtipSnapshot(next);
      });
  }

  private refreshGlitchtipEvents(): void {
    this.glitchtipService.getRecentEvents().pipe(
      catchError(() => of<ErrorLogEntry[] | null>(null)),
      takeUntil(this.destroy$),
    ).subscribe((rows) => {
      if (rows) this.applyGlitchtipSnapshot(rows);
    });
  }

  private applyGlitchtipSnapshot(rows: ErrorLogEntry[]): void {
    this.glitchtipEvents = Array.isArray(rows) ? rows.filter((entry) => !entry.acknowledged) : [];
    this.glitchtipLastSyncedAt = new Date().toISOString();
  }

  private reconcileErrorSnapshot(next: ErrorLogEntry[]): void {
    const diff = diffErrorSnapshot(this.errors, next);
    this.errors = diff.unack;
    this.acknowledgedErrors = diff.ack;
    if (!diff.priorityArrival) return;
    window.setTimeout(() => {
      this.scrollAttention.drawTo(`#error-${diff.priorityArrival!.id}`, {
        priority: 'urgent',
        announce: `New ${diff.priorityArrival!.severity} error in ${diff.priorityArrival!.job_type}.`,
      });
    }, 0);
  }

  loadData(): void {
    this.loading = true;
    forkJoin({
      services: this.diagnosticsService.getServices(),
      conflicts: this.diagnosticsService.getConflicts(),
      features: this.diagnosticsService.getFeatures(),
      resources: this.diagnosticsService.getResources(),
      errors: this.diagnosticsService.getErrors().pipe(catchError(() => of<ErrorLogEntry[]>([]))),
      runtimeCtx: this.diagnosticsService.getRuntimeContext().pipe(catchError(() => of<RuntimeContext | null>(null))),
      nodes: this.diagnosticsService.getNodes().pipe(catchError(() => of<NodeSummary[]>([]))),
      pipelineGate: this.diagnosticsService.getPipelineGate().pipe(catchError(() => of<PipelineGate | null>(null))),
      ndcgEval: this.diagnosticsService.getNdcgEval().pipe(catchError(() => of<NdcgEvalResult | null>(null))),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.services = data.services;
        this.conflicts = data.conflicts;
        this.features = data.features;
        this.resources = data.resources;
        this.runtimeCtx = data.runtimeCtx;
        this.nodes = data.nodes;
        this.pipelineGate = data.pipelineGate;
        this.ndcgEval = data.ndcgEval;
        this.applyErrorsSnapshot(data.errors);
        this.rebuildRuntimeCards();
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading diagnostics data', err);
        this.loading = false;
      },
    });
  }

  private applyErrorsSnapshot(rows: ErrorLogEntry[]): void {
    const all = Array.isArray(rows) ? rows : [];
    this.errors = all.filter((entry) => !entry.acknowledged);
    this.acknowledgedErrors = all.filter((entry) => entry.acknowledged);
  }

  refreshAll(): void {
    this.refreshing = true;
    forkJoin({
      services: this.diagnosticsService.refreshServices(),
      conflicts: this.diagnosticsService.detectConflicts(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.loadData();
        if (this.selectedErrorTabIndex === GLITCHTIP_TAB_INDEX) this.refreshGlitchtipEvents();
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Error refreshing diagnostics', err);
        this.refreshing = false;
      },
    });
  }

  private subscribeToRealtimeUpdates(): void {
    this.realtime.subscribeTopic('diagnostics').pipe(takeUntil(this.destroy$)).subscribe((update: TopicUpdate) => {
      this.handleRealtimeUpdate(update);
    });
  }

  private handleRealtimeUpdate(update: TopicUpdate): void {
    dispatchRealtimeUpdate(update, {
      onServiceUpsert: (next) => this.upsertService(next),
      onServiceRemove: (id) => this.removeService(id),
      onConflictUpsert: (next) => this.upsertConflict(next),
      onConflictRemove: (id) => this.removeConflict(id),
    });
  }

  private rebuildRuntimeCards(): void {
    this.runtimeLaneCards = buildRuntimeLaneCards(this.services);
    this.runtimeExecutionCards = buildRuntimeExecutionCards(this.services);
  }

  private upsertService(next: ServiceStatus): void {
    const { services, pulse } = upsertServiceInto(this.services, next);
    this.services = services;
    this.rebuildRuntimeCards();
    if (pulse) this.scrollAttention.drawTo(pulse.selector, { priority: 'urgent', announce: pulse.announce });
  }

  private removeService(id: number): void {
    this.services = removeServiceFrom(this.services, id);
    this.rebuildRuntimeCards();
  }

  private upsertConflict(next: SystemConflict): void {
    const { conflicts, pulse } = upsertConflictInto(this.conflicts, next);
    this.conflicts = conflicts;
    if (pulse) this.scrollAttention.drawTo(pulse.selector, { priority: 'urgent', announce: pulse.announce });
  }

  private removeConflict(id: number): void {
    this.conflicts = removeConflictFrom(this.conflicts, id);
  }

  onResolveConflict(id: number): void {
    this.diagnosticsService.resolveConflict(id).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.conflicts = this.conflicts.filter((conflict) => conflict.id !== id);
    });
  }

  getHealthyCount(): number { return this.services.filter((service) => service.state === 'healthy').length; }
  runtimeLaneTrackBy(_i: number, lane: RuntimeLaneCard): string { return lane.id; }
  runtimeExecutionTrackBy(_i: number, card: RuntimeExecutionCard): string { return card.id; }

  /** Polish.B — turn the NDCG breakdown dict into a sorted list for *ngFor. */
  ndcgEvalOriginEntries(): Array<{ origin: string; score: number }> {
    const breakdown = this.ndcgEval?.breakdown_by_candidate_origin;
    if (!breakdown) {
      return [];
    }
    return Object.entries(breakdown)
      .map(([origin, score]) => ({ origin, score: score as number }))
      .sort((a, b) => b.score - a.score);
  }
  trackServiceName(_i: number, service: ServiceStatus): string { return service.service_name; }
  get coreServices(): ServiceStatus[] { return this.services.filter((service) => !RUNTIME_SUMMARY_SERVICES.has(service.service_name)); }
  get groupedErrors(): ErrorGroup[] { return groupErrors(this.errors, this.filterNodeId); }

  get activeGroupedErrors(): ErrorGroup[] {
    if (this.selectedErrorTabIndex === 0) {
      return groupErrors(this.errors.filter((entry) => entry.source !== 'glitchtip'), this.filterNodeId);
    }
    if (this.selectedErrorTabIndex === GLITCHTIP_TAB_INDEX) {
      return groupErrors(this.glitchtipEvents, this.filterNodeId);
    }
    return this.groupedErrors;
  }

  get showAcknowledgedDrawer(): boolean { return this.selectedErrorTabIndex === 2 && this.acknowledgedErrors.length > 0; }
  uniqueNodes(): string[] { return uniqueNodeIds(this.errors); }
  maxTrendCount(trend: { count: number }[] | undefined): number { return maxTrendCountFn(trend); }
  relatedErrors(error: ErrorLogEntry): ErrorLogEntry[] { return relatedErrorsFn(error, this.errors); }
  trendLabel(trend: { date: string; count: number }[] | undefined): string { return trendLabelFn(trend); }
  trackGroupFingerprint = trackGroupFingerprintFn;
  trackErrorId = trackErrorIdFn;
  trackNodeId = trackNodeIdFn;
  trackTrendDate = trackTrendDateFn;

  onAcknowledgeError(error: ErrorLogEntry): void {
    const wasExpanded = this.expandedErrorId === error.id;
    const glitchtipIndex = this.glitchtipEvents.findIndex((row) => row.id === error.id);
    this.errors = this.errors.filter((row) => row.id !== error.id);
    if (glitchtipIndex !== -1) this.glitchtipEvents = this.glitchtipEvents.filter((row) => row.id !== error.id);
    this.acknowledgedErrors = [{ ...error, acknowledged: true }, ...this.acknowledgedErrors];
    if (wasExpanded) this.expandedErrorId = null;
    this.diagnosticsService.acknowledgeError(error.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {},
      error: () => {
        this.acknowledgedErrors = this.acknowledgedErrors.filter((row) => row.id !== error.id);
        this.errors = [error, ...this.errors];
        if (glitchtipIndex !== -1) {
          const restored = [...this.glitchtipEvents];
          restored.splice(glitchtipIndex, 0, error);
          this.glitchtipEvents = restored;
        }
        this.snack.open('Could not acknowledge that error. Please try again.', 'Dismiss', { duration: 5000 });
      },
    });
  }

  onRerunError(error: ErrorLogEntry): void {
    this.diagnosticsService.rerunError(error.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result) => {
        if (result.status === 'queued') {
          this.snack.open(`Re-dispatched ${error.job_type} Â· ${error.step}. Acknowledging this error.`, 'Dismiss', { duration: 4000 });
          this.onAcknowledgeError(error);
          return;
        }
        this.snack.open(`Rerun response: ${result.status}`, 'Dismiss', { duration: 4000 });
      },
      error: (err) => {
        const detail = (err?.error?.detail as string | undefined) ?? 'Please check the backend logs.';
        this.snack.open(`Rerun failed: ${detail}`, 'Dismiss', { duration: 6000 });
      },
    });
  }

  toggleExpand(id: number): void { this.expandedErrorId = this.expandedErrorId === id ? null : id; }
  toggleNodeFilter(nodeId: string | null): void { this.filterNodeId = this.filterNodeId === nodeId ? null : nodeId; }
  openDjangoAdmin(): void { window.open(this.adminUrl, '_blank', 'noopener,noreferrer'); }
  openGlitchtip(): void { window.open(this.glitchtipBaseUrl, '_blank', 'noopener,noreferrer'); }
  onErrorTabChange(index: number): void {
    this.selectedErrorTabIndex = index;
    if (index === GLITCHTIP_TAB_INDEX) this.refreshGlitchtipEvents();
  }

  copyForAI(error: ErrorLogEntry): void {
    const prompt = buildAIPromptForError(error);
    const onSuccess = () => {
      this.copyFeedbackId = error.id;
      this.snack.open('Copied AI-ready prompt to clipboard.', 'Dismiss', { duration: 2000 });
      window.setTimeout(() => {
        if (this.copyFeedbackId === error.id) this.copyFeedbackId = null;
      }, 1500);
    };
    const onFail = () => {
      this.snack.open('Could not access the clipboard.', 'Dismiss', { duration: 4000 });
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(prompt).then(onSuccess).catch(onFail);
      return;
    }
    onFail();
  }

  canRerun(error: ErrorLogEntry): boolean { return ['pipeline', 'sync', 'import'].includes(error.job_type); }
  severityClass(error: ErrorLogEntry): string { return `severity-${error.severity ?? 'medium'}`; }
  nodeToneClass(node: NodeSummary): string {
    if (node.worst_severity === 'critical') return 'tone-bad';
    return node.unacknowledged > 0 ? 'tone-warn' : 'tone-good';
  }
  trackByIndex(index: number): number { return index; }
  trackByLabel(_: number, item: { label: string }): string { return item.label; }
}
