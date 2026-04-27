import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
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
    MatCardModule,
    PersistTabDirective, ServiceCardComponent, ConflictListComponent,
    ReadinessMatrixComponent, SuppressedPairsCardComponent,
  ],
  templateUrl: './diagnostics.component.html',
  styleUrls: ['./diagnostics.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
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

  // ── Server-truth signals ────────────────────────────────────────
  readonly services = signal<ServiceStatus[]>([]);
  readonly conflicts = signal<SystemConflict[]>([]);
  readonly features = signal<FeatureReadiness[]>([]);
  readonly resources = signal<ResourceUsage | null>(null);
  /** Polish.B — populated daily by the ndcg_smoke_test scheduled job. */
  readonly ndcgEval = signal<NdcgEvalResult | null>(null);
  readonly loading = signal(true);
  readonly refreshing = signal(false);
  readonly errors = signal<ErrorLogEntry[]>([]);
  readonly acknowledgedErrors = signal<ErrorLogEntry[]>([]);
  readonly runtimeCtx = signal<RuntimeContext | null>(null);
  readonly glitchtipEvents = signal<ErrorLogEntry[]>([]);
  readonly glitchtipLastSyncedAt = signal<string | null>(null);
  readonly nodes = signal<NodeSummary[]>([]);
  readonly pipelineGate = signal<PipelineGate | null>(null);

  // ── UI state signals ────────────────────────────────────────────
  readonly selectedErrorTabIndex = signal(0);
  readonly expandedErrorId = signal<number | null>(null);
  readonly filterNodeId = signal<string | null>(null);
  readonly copyFeedbackId = signal<number | null>(null);

  // ── Static config ──────────────────────────────────────────────
  readonly adminUrl = environment.adminUrl;
  readonly glitchtipBaseUrl = environment.glitchtipBaseUrl;

  // ── Derived state (replaces imperative rebuildRuntimeCards + getters) ──
  // The previous component called `rebuildRuntimeCards()` from loadData,
  // upsertService, and removeService — three places that had to remember
  // to fire after every services mutation. Now lane and execution cards
  // recompute automatically off `services()` and the imperative method
  // is gone.
  readonly runtimeLaneCards = computed<RuntimeLaneCard[]>(() => buildRuntimeLaneCards(this.services()));
  readonly runtimeExecutionCards = computed<RuntimeExecutionCard[]>(() => buildRuntimeExecutionCards(this.services()));

  readonly healthyCount = computed(() =>
    this.services().filter((service) => service.state === 'healthy').length,
  );

  readonly coreServices = computed(() =>
    this.services().filter((service) => !RUNTIME_SUMMARY_SERVICES.has(service.service_name)),
  );

  readonly groupedErrors = computed(() => groupErrors(this.errors(), this.filterNodeId()));

  readonly activeGroupedErrors = computed<ErrorGroup[]>(() => {
    const filterNode = this.filterNodeId();
    const tabIndex = this.selectedErrorTabIndex();
    if (tabIndex === 0) {
      return groupErrors(this.errors().filter((entry) => entry.source !== 'glitchtip'), filterNode);
    }
    if (tabIndex === GLITCHTIP_TAB_INDEX) {
      return groupErrors(this.glitchtipEvents(), filterNode);
    }
    return this.groupedErrors();
  });

  readonly showAcknowledgedDrawer = computed(() =>
    this.selectedErrorTabIndex() === 2 && this.acknowledgedErrors().length > 0,
  );

  readonly uniqueNodes = computed<string[]>(() => uniqueNodeIds(this.errors()));

  readonly ndcgEvalOriginEntries = computed<Array<{ origin: string; score: number }>>(() => {
    const breakdown = this.ndcgEval()?.breakdown_by_candidate_origin;
    if (!breakdown) return [];
    return Object.entries(breakdown)
      .map(([origin, score]) => ({ origin, score: score as number }))
      .sort((a, b) => b.score - a.score);
  });

  ngOnInit(): void {
    this.route.fragment.pipe(takeUntil(this.destroy$)).subscribe((fragment) => {
      if (!fragment || !(fragment in ERROR_TAB_FRAGMENT_TO_INDEX)) return;
      const idx = ERROR_TAB_FRAGMENT_TO_INDEX[fragment];
      this.selectedErrorTabIndex.set(idx);
      if (idx === GLITCHTIP_TAB_INDEX) this.refreshGlitchtipEvents();
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
    // Gated by `VisibilityGateService`. The inner switchMap reads the
    // current tab signal each tick — when the user is on a non-glitchtip
    // tab the inner returns `of(null)` so we don't waste a fetch.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(30_000, 30_000).pipe(
          switchMap(() =>
            this.selectedErrorTabIndex() === GLITCHTIP_TAB_INDEX
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
    this.glitchtipEvents.set(
      Array.isArray(rows) ? rows.filter((entry) => !entry.acknowledged) : [],
    );
    this.glitchtipLastSyncedAt.set(new Date().toISOString());
  }

  private reconcileErrorSnapshot(next: ErrorLogEntry[]): void {
    const diff = diffErrorSnapshot(this.errors(), next);
    this.errors.set(diff.unack);
    this.acknowledgedErrors.set(diff.ack);
    if (!diff.priorityArrival) return;
    // Fire the scroll-attention pulse on the next event-loop tick so
    // the DOM has had a chance to render the new error row first.
    window.setTimeout(() => {
      this.scrollAttention.drawTo(`#error-${diff.priorityArrival!.id}`, {
        priority: 'urgent',
        announce: `New ${diff.priorityArrival!.severity} error in ${diff.priorityArrival!.job_type}.`,
      });
    }, 0);
  }

  loadData(): void {
    this.loading.set(true);
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
        this.services.set(data.services);
        this.conflicts.set(data.conflicts);
        this.features.set(data.features);
        this.resources.set(data.resources);
        this.runtimeCtx.set(data.runtimeCtx);
        this.nodes.set(data.nodes);
        this.pipelineGate.set(data.pipelineGate);
        this.ndcgEval.set(data.ndcgEval);
        this.applyErrorsSnapshot(data.errors);
        // Runtime cards are computed() now — no rebuildRuntimeCards() call needed.
        this.loading.set(false);
      },
      error: (err) => {
        console.error('Error loading diagnostics data', err);
        this.loading.set(false);
      },
    });
  }

  private applyErrorsSnapshot(rows: ErrorLogEntry[]): void {
    const all = Array.isArray(rows) ? rows : [];
    this.errors.set(all.filter((entry) => !entry.acknowledged));
    this.acknowledgedErrors.set(all.filter((entry) => entry.acknowledged));
  }

  refreshAll(): void {
    this.refreshing.set(true);
    forkJoin({
      services: this.diagnosticsService.refreshServices(),
      conflicts: this.diagnosticsService.detectConflicts(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.loadData();
        if (this.selectedErrorTabIndex() === GLITCHTIP_TAB_INDEX) this.refreshGlitchtipEvents();
        this.refreshing.set(false);
      },
      error: (err) => {
        console.error('Error refreshing diagnostics', err);
        this.refreshing.set(false);
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

  private upsertService(next: ServiceStatus): void {
    const { services, pulse } = upsertServiceInto(this.services(), next);
    this.services.set(services);
    // Runtime cards are computed() over services() — recompute is automatic.
    if (pulse) this.scrollAttention.drawTo(pulse.selector, { priority: 'urgent', announce: pulse.announce });
  }

  private removeService(id: number): void {
    this.services.set(removeServiceFrom(this.services(), id));
  }

  private upsertConflict(next: SystemConflict): void {
    const { conflicts, pulse } = upsertConflictInto(this.conflicts(), next);
    this.conflicts.set(conflicts);
    if (pulse) this.scrollAttention.drawTo(pulse.selector, { priority: 'urgent', announce: pulse.announce });
  }

  private removeConflict(id: number): void {
    this.conflicts.set(removeConflictFrom(this.conflicts(), id));
  }

  onResolveConflict(id: number): void {
    this.diagnosticsService.resolveConflict(id).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.conflicts.update((arr) => arr.filter((conflict) => conflict.id !== id));
    });
  }

  // ── Trackers / template helpers ────────────────────────────────
  runtimeLaneTrackBy(_i: number, lane: RuntimeLaneCard): string { return lane.id; }
  runtimeExecutionTrackBy(_i: number, card: RuntimeExecutionCard): string { return card.id; }
  trackServiceName(_i: number, service: ServiceStatus): string { return service.service_name; }

  maxTrendCount(trend: { count: number }[] | undefined): number { return maxTrendCountFn(trend); }
  relatedErrors(error: ErrorLogEntry): ErrorLogEntry[] { return relatedErrorsFn(error, this.errors()); }
  trendLabel(trend: { date: string; count: number }[] | undefined): string { return trendLabelFn(trend); }
  trackGroupFingerprint = trackGroupFingerprintFn;
  trackErrorId = trackErrorIdFn;
  trackNodeId = trackNodeIdFn;
  trackTrendDate = trackTrendDateFn;

  onAcknowledgeError(error: ErrorLogEntry): void {
    const wasExpanded = this.expandedErrorId() === error.id;
    // Capture the optimistic snapshots so we can revert atomically on error.
    // Previously the revert path read `this.errors`/`this.glitchtipEvents`
    // again — under signals that's still correct because the writes haven't
    // reached the server yet, but capturing once makes the revert path
    // independent of any mid-flight reordering.
    const errorsBefore = this.errors();
    const ackBefore = this.acknowledgedErrors();
    const glitchtipBefore = this.glitchtipEvents();
    const glitchtipIndex = glitchtipBefore.findIndex((row) => row.id === error.id);

    this.errors.update((arr) => arr.filter((row) => row.id !== error.id));
    if (glitchtipIndex !== -1) {
      this.glitchtipEvents.update((arr) => arr.filter((row) => row.id !== error.id));
    }
    this.acknowledgedErrors.update((arr) => [{ ...error, acknowledged: true }, ...arr]);
    if (wasExpanded) this.expandedErrorId.set(null);

    this.diagnosticsService.acknowledgeError(error.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => { /* server confirmed — optimistic state is now authoritative */ },
      error: () => {
        // Revert to captured pre-mutation snapshots.
        this.errors.set(errorsBefore);
        this.acknowledgedErrors.set(ackBefore);
        this.glitchtipEvents.set(glitchtipBefore);
        this.snack.open('Could not acknowledge that error. Please try again.', 'Dismiss', { duration: 5000 });
      },
    });
  }

  onRerunError(error: ErrorLogEntry): void {
    this.diagnosticsService.rerunError(error.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result) => {
        if (result.status === 'queued') {
          this.snack.open(`Re-dispatched ${error.job_type} · ${error.step}. Acknowledging this error.`, 'Dismiss', { duration: 4000 });
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

  toggleExpand(id: number): void {
    this.expandedErrorId.update((curr) => curr === id ? null : id);
  }

  toggleNodeFilter(nodeId: string | null): void {
    this.filterNodeId.update((curr) => curr === nodeId ? null : nodeId);
  }

  openDjangoAdmin(): void { window.open(this.adminUrl, '_blank', 'noopener,noreferrer'); }
  openGlitchtip(): void { window.open(this.glitchtipBaseUrl, '_blank', 'noopener,noreferrer'); }

  onErrorTabChange(index: number): void {
    this.selectedErrorTabIndex.set(index);
    if (index === GLITCHTIP_TAB_INDEX) this.refreshGlitchtipEvents();
  }

  copyForAI(error: ErrorLogEntry): void {
    const prompt = buildAIPromptForError(error);
    const onSuccess = () => {
      this.copyFeedbackId.set(error.id);
      this.snack.open('Copied AI-ready prompt to clipboard.', 'Dismiss', { duration: 2000 });
      // Use a cancellable RxJS timer so a route-leave during the 1.5s
      // window doesn't fire a setter on a dead component. The outer
      // `takeUntil(destroy$)` aborts it cleanly.
      timer(1500).pipe(takeUntil(this.destroy$)).subscribe(() => {
        if (this.copyFeedbackId() === error.id) this.copyFeedbackId.set(null);
      });
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
