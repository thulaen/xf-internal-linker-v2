import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import {
  DiagnosticsService,
  ServiceStatus,
  SystemConflict,
  FeatureReadiness,
  ResourceUsage,
  ErrorLogEntry,
  RuntimeContext,
  NodeSummary,
  PipelineGate,
  SuppressedPairsDiagnostics,
} from './diagnostics.service';
import { ServiceCardComponent } from './service-card/service-card.component';
import { ConflictListComponent } from './conflict-list/conflict-list.component';
import { ReadinessMatrixComponent } from './readiness-matrix/readiness-matrix.component';
import { MetaTournamentComponent } from './meta-tournament/meta-tournament.component';
import {
  RuntimeLaneCard,
  RuntimeExecutionCard,
  buildRuntimeLaneCards,
  buildRuntimeExecutionCards,
} from './diagnostics.runtime-cards';
import {
  ErrorGroup,
  groupErrors,
  uniqueNodeIds,
  maxTrendCount as maxTrendCountFn,
  relatedErrors as relatedErrorsFn,
  trendLabel as trendLabelFn,
  trackGroupFingerprint as trackGroupFingerprintFn,
  trackErrorId as trackErrorIdFn,
  trackNodeId as trackNodeIdFn,
  trackTrendDate as trackTrendDateFn,
  buildAIPromptForError,
  diffErrorSnapshot,
} from './diagnostics.error-log';
import {
  dispatchRealtimeUpdate,
  upsertServiceInto,
  removeServiceFrom,
  upsertConflictInto,
  removeConflictFrom,
} from './diagnostics.realtime';
import { forkJoin, Subject, catchError, of, takeUntil, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { RealtimeService } from '../core/services/realtime.service';
import { ScrollAttentionService } from '../core/services/scroll-attention.service';
import { TopicUpdate } from '../core/services/realtime.types';
import { environment } from '../../environments/environment';

const RUNTIME_SUMMARY_SERVICES = new Set([
  'runtime_lanes', 'native_scoring', 'slate_diversity_runtime',
  'embedding_specialist', 'scheduler_lane',
]);

@Component({
  selector: 'app-diagnostics',
  standalone: true,
  imports: [
    CommonModule,
    MatTooltipModule,
    MatButtonModule,
    MatIconModule,
    ServiceCardComponent,
    ConflictListComponent,
    ReadinessMatrixComponent,
    MetaTournamentComponent,
  ],
  templateUrl: './diagnostics.component.html',
  styleUrls: ['./diagnostics.component.scss']
})
export class DiagnosticsComponent implements OnInit, OnDestroy {
  private diagnosticsService = inject(DiagnosticsService);
  private realtime = inject(RealtimeService);
  private scrollAttention = inject(ScrollAttentionService);
  private snack = inject(MatSnackBar);
  private destroy$ = new Subject<void>();

  services: ServiceStatus[] = [];
  conflicts: SystemConflict[] = [];
  features: FeatureReadiness[] = [];
  resources: ResourceUsage | null = null;
  runtimeLaneCards: RuntimeLaneCard[] = [];
  runtimeExecutionCards: RuntimeExecutionCard[] = [];
  loading = true;
  refreshing = false;

  // ────────────────────────────────────────────────────────────────
  // Phase GT Step 11 — Error Log section state
  // ────────────────────────────────────────────────────────────────

  /** Unacknowledged errors. Split from `acknowledgedErrors` on every refresh
   *  so the two sections render without filtering per keystroke. */
  errors: ErrorLogEntry[] = [];
  acknowledgedErrors: ErrorLogEntry[] = [];

  /** Current-node snapshot for the Live Runtime Health strip (GT-G9). */
  runtimeCtx: RuntimeContext | null = null;

  /**
   * Phase 1v — Phase 1 negative-memory (RejectedPair) counters for the
   * "Suppressed pairs" card. Null when the endpoint errors — the card hides
   * itself rather than showing zeros that might be mistaken for real data.
   */
  suppressedPairs: SuppressedPairsDiagnostics | null = null;

  /** One row per known node, populated by /api/system/status/nodes/ (GT-G13).
   *  Only rendered when length > 1 — a single-host install keeps it quiet. */
  nodes: NodeSummary[] = [];

  /** Single go/no-go verdict from /api/system/status/pipeline-gate/ (GT-G14).
   *  Banner only shows when can_run === false. */
  pipelineGate: PipelineGate | null = null;

  /** Id of the error row whose Details panel is currently expanded; `null`
   *  means all collapsed. Only one expanded at a time so the page doesn't
   *  grow unbounded during triage. */
  expandedErrorId: number | null = null;

  /** Active node filter — `null` means "all nodes". Clicking a node card
   *  (GT-G13) or a chip (GT-G7) sets this. */
  filterNodeId: string | null = null;

  /** Non-null while the Copy-for-AI button shows its ✓ pulse. Keyed on
   *  error id so only the button that was pressed shows the confirm. */
  copyFeedbackId: number | null = null;

  /** Shortcut for template-side links. */
  readonly adminUrl = environment.adminUrl;
  readonly glitchtipUrl = 'http://localhost:1337';

  ngOnInit(): void {
    this.loadData();
    this.subscribeToRealtimeUpdates();
    this.startErrorLogPoll();
  }

  /**
   * Phase GT Step 11 — error-log refresh poll.
   *
   * The `diagnostics` realtime topic (Phase R1) broadcasts on
   * `ServiceStatusSnapshot` and `SystemConflict` changes only — NOT on
   * `ErrorLog` rows, by design (per-error broadcasts would be too chatty
   * during a looping failure). We refresh the list every 30 seconds while
   * the page is open and fire the Scroll-to-Attention service when a NEW
   * critical/high error arrives that wasn't in the previous snapshot.
   *
   * Future-proof hook: when an `errors.log` realtime topic lands (Phase U2
   * throttled batch broadcast), this poll becomes a fallback instead of
   * the primary path — drop the interval to 120s and keep the diff logic.
   */
  private startErrorLogPoll(): void {
    // Start after 30s (loadData already populated the first snapshot).
    timer(30_000, 30_000)
      .pipe(
        switchMap(() =>
          this.diagnosticsService
            .getErrors()
            .pipe(catchError(() => of<ErrorLogEntry[] | null>(null))),
        ),
        takeUntil(this.destroy$),
      )
      .subscribe((next) => {
        if (!next) return;
        this.reconcileErrorSnapshot(next);
      });
  }

  /**
   * Merge an incoming errors list with the current state. New high- or
   * critical-severity rows (never seen before) trigger Scroll-to-Attention
   * so the operator is pulled to them. Existing rows just update their
   * counts/messages in place.
   */
  private reconcileErrorSnapshot(next: ErrorLogEntry[]): void {
    const diff = diffErrorSnapshot(this.errors, next);
    this.errors = diff.unack;
    this.acknowledgedErrors = diff.ack;
    if (!diff.priorityArrival) return;
    const target = diff.priorityArrival;
    // Defer one tick so Angular has rendered the new <article id="error-{id}">
    // by the time we call scrollIntoView.
    window.setTimeout(() => {
      this.scrollAttention.drawTo(`#error-${target.id}`, {
        priority: 'urgent',
        announce: `New ${target.severity} error in ${target.job_type}.`,
      });
    }, 0);
  }

  loadData(): void {
    this.loading = true;
    // Per-stream catchError prevents a single failing endpoint from
    // blanking the page — critical during worker restarts.
    forkJoin({
      services: this.diagnosticsService.getServices(),
      conflicts: this.diagnosticsService.getConflicts(),
      features: this.diagnosticsService.getFeatures(),
      resources: this.diagnosticsService.getResources(),
      errors: this.diagnosticsService.getErrors().pipe(catchError(() => of<ErrorLogEntry[]>([]))),
      runtimeCtx: this.diagnosticsService.getRuntimeContext().pipe(catchError(() => of<RuntimeContext | null>(null))),
      nodes: this.diagnosticsService.getNodes().pipe(catchError(() => of<NodeSummary[]>([]))),
      pipelineGate: this.diagnosticsService.getPipelineGate().pipe(catchError(() => of<PipelineGate | null>(null))),
      suppressedPairs: this.diagnosticsService.getSuppressedPairs().pipe(catchError(() => of<SuppressedPairsDiagnostics | null>(null))),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.services = data.services;
        this.conflicts = data.conflicts;
        this.features = data.features;
        this.resources = data.resources;
        this.rebuildRuntimeCards();
        this.applyErrorsSnapshot(data.errors);
        this.runtimeCtx = data.runtimeCtx;
        this.nodes = data.nodes;
        this.pipelineGate = data.pipelineGate;
        this.suppressedPairs = data.suppressedPairs;
        this.loading = false;
      },
      error: (err) => {
        // This path is reached only if the FIRST four (required) calls
        // error out — the new GT calls all use per-stream catchError.
        console.error('Error loading diagnostics data', err);
        this.loading = false;
      }
    });
  }

  /** Split a flat ErrorLog list into unacknowledged vs acknowledged.
   *  Kept as its own method so realtime updates can reuse it later. */
  private applyErrorsSnapshot(rows: ErrorLogEntry[]): void {
    const all = Array.isArray(rows) ? rows : [];
    this.errors = all.filter((e) => !e.acknowledged);
    this.acknowledgedErrors = all.filter((e) => e.acknowledged);
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

  /**
   * Phase R1.1 — live updates from the generic `/ws/realtime/` stream.
   * Replaces the "click Run New Check to see changes" flow that caused the
   * stale-C#-tile bug. On every broadcast, the relevant array is updated in
   * place and derived card lists are rebuilt. A service that newly failed
   * triggers scroll-to-attention so the user sees it immediately.
   */
  private subscribeToRealtimeUpdates(): void {
    this.realtime
      .subscribeTopic('diagnostics')
      .pipe(takeUntil(this.destroy$))
      .subscribe((update: TopicUpdate) => this.handleRealtimeUpdate(update));
  }

  private handleRealtimeUpdate(update: TopicUpdate): void {
    dispatchRealtimeUpdate(update, {
      onServiceUpsert: next => this.upsertService(next),
      onServiceRemove: id => this.removeService(id),
      onConflictUpsert: next => this.upsertConflict(next),
      onConflictRemove: id => this.removeConflict(id),
    });
  }

  private rebuildRuntimeCards(): void {
    this.rebuildRuntimeCards();
  }

  private upsertService(next: ServiceStatus): void {
    const { services, pulse } = upsertServiceInto(this.services, next);
    this.services = services;
    this.rebuildRuntimeCards();
    if (pulse) {
      this.scrollAttention.drawTo(pulse.selector, { priority: 'urgent', announce: pulse.announce });
    }
  }

  private removeService(id: number): void {
    this.services = removeServiceFrom(this.services, id);
    this.rebuildRuntimeCards();
  }

  private upsertConflict(next: SystemConflict): void {
    const { conflicts, pulse } = upsertConflictInto(this.conflicts, next);
    this.conflicts = conflicts;
    if (pulse) {
      this.scrollAttention.drawTo(pulse.selector, { priority: 'urgent', announce: pulse.announce });
    }
  }

  private removeConflict(id: number): void {
    this.conflicts = removeConflictFrom(this.conflicts, id);
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

  getHealthyCount(): number { return this.services.filter(s => s.state === 'healthy').length; }
  runtimeLaneTrackBy(_i: number, lane: RuntimeLaneCard): string { return lane.id; }
  runtimeExecutionTrackBy(_i: number, card: RuntimeExecutionCard): string { return card.id; }
  trackServiceName(_i: number, s: ServiceStatus): string { return s.service_name; }

  get coreServices(): ServiceStatus[] {
    return this.services.filter(s => !RUNTIME_SUMMARY_SERVICES.has(s.service_name));
  }

  // ────────────────────────────────────────────────────────────────
  // Phase GT Step 11 — Error Log derived state + helpers
  // ────────────────────────────────────────────────────────────────

  /**
   * Group errors by fingerprint so the UI renders one row per distinct
   * failure instead of 50 rows for the same looping error. Unfingerprinted
   * rows (rare, pre-Phase-GT) each get their own synthetic bucket keyed on
   * `unique-{id}` so the template can still `track` them.
   *
   * Honors the `filterNodeId` node selection. Computed as a getter on every
   * change detection tick — cheap for <500 errors, which is the soft cap
   * the Error Log pagination is designed for.
   */
  get groupedErrors(): ErrorGroup[] {
    return groupErrors(this.errors, this.filterNodeId);
  }

  uniqueNodes(): string[] {
    return uniqueNodeIds(this.errors);
  }

  maxTrendCount(trend: { count: number }[] | undefined): number {
    return maxTrendCountFn(trend);
  }

  relatedErrors(e: ErrorLogEntry): ErrorLogEntry[] {
    return relatedErrorsFn(e, this.errors);
  }

  trendLabel(trend: { date: string; count: number }[] | undefined): string {
    return trendLabelFn(trend);
  }

  trackGroupFingerprint = trackGroupFingerprintFn;
  trackErrorId = trackErrorIdFn;
  trackNodeId = trackNodeIdFn;
  trackTrendDate = trackTrendDateFn;

  // ────────────────────────────────────────────────────────────────
  // Phase GT Step 11 — Error Log event handlers
  // ────────────────────────────────────────────────────────────────

  /** Acknowledge a single error. Optimistically moves the row between the
   *  two lists so the UI reacts instantly; on HTTP failure the snackbar
   *  explains and the row stays where it was. */
  onAcknowledgeError(e: ErrorLogEntry): void {
    const wasExpanded = this.expandedErrorId === e.id;
    // Optimistic move — remove from unack, prepend to acknowledged.
    this.errors = this.errors.filter((x) => x.id !== e.id);
    const moved: ErrorLogEntry = { ...e, acknowledged: true };
    this.acknowledgedErrors = [moved, ...this.acknowledgedErrors];
    if (wasExpanded) this.expandedErrorId = null;

    this.diagnosticsService
      .acknowledgeError(e.id)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => {
          // Server agreed — nothing to do.
        },
        error: () => {
          // Rollback.
          this.acknowledgedErrors = this.acknowledgedErrors.filter((x) => x.id !== e.id);
          this.errors = [e, ...this.errors];
          this.snack.open(
            'Could not acknowledge that error. Please try again.',
            'Dismiss',
            { duration: 5000 },
          );
        },
      });
  }

  /** Re-dispatch the Celery task behind a pipeline/sync/import error.
   *  Disabled in the template for job types outside the backend whitelist
   *  so we never surprise-fire something non-recoverable. Auto-acknowledges
   *  on successful queue. */
  onRerunError(e: ErrorLogEntry): void {
    this.diagnosticsService
      .rerunError(e.id)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (result) => {
          if (result.status === 'queued') {
            this.snack.open(
              `Re-dispatched ${e.job_type} · ${e.step}. Acknowledging this error.`,
              'Dismiss',
              { duration: 4000 },
            );
            this.onAcknowledgeError(e);
          } else {
            this.snack.open(
              `Rerun response: ${result.status}`,
              'Dismiss',
              { duration: 4000 },
            );
          }
        },
        error: (err) => {
          const detail =
            (err?.error?.detail as string | undefined) ?? 'Please check the backend logs.';
          this.snack.open(`Rerun failed: ${detail}`, 'Dismiss', { duration: 6000 });
        },
      });
  }

  /** Details-panel toggle (only one open at a time), node-card filter toggle,
   *  and Django Admin shortcut. `noopener,noreferrer` on the admin window
   *  is mandatory per the privacy-protection rules. */
  toggleExpand(id: number): void { this.expandedErrorId = this.expandedErrorId === id ? null : id; }
  toggleNodeFilter(nodeId: string | null): void { this.filterNodeId = this.filterNodeId === nodeId ? null : nodeId; }
  openDjangoAdmin(): void { window.open(this.adminUrl, '_blank', 'noopener,noreferrer'); }

  /**
   * GT-G2 — build an AI-ready prompt for the error and copy to clipboard.
   * The resulting text is self-contained: an engineer can paste it into
   * Claude/Codex/ChatGPT with no additional context. Runtime snapshot
   * and traceback (when present) are inlined so the LLM sees the full
   * picture without leaking secrets beyond what's already in the error.
   */
  copyForAI(e: ErrorLogEntry): void {
    const prompt = buildAIPromptForError(e);
    const onSuccess = () => {
      this.copyFeedbackId = e.id;
      this.snack.open('Copied AI-ready prompt to clipboard.', 'Dismiss', { duration: 2000 });
      window.setTimeout(() => {
        if (this.copyFeedbackId === e.id) this.copyFeedbackId = null;
      }, 1500);
    };
    const onFail = () => {
      this.snack.open('Could not access the clipboard.', 'Dismiss', { duration: 4000 });
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(prompt).then(onSuccess).catch(onFail);
    } else {
      onFail();
    }
  }

  /** Rerun eligibility, severity stripe, and node-card tone — centralised
   *  so the template stays readable and new job types are trivial to add. */
  canRerun(e: ErrorLogEntry): boolean { return ['pipeline', 'sync', 'import'].includes(e.job_type); }
  severityClass(e: ErrorLogEntry): string { return `severity-${e.severity ?? 'medium'}`; }
  nodeToneClass(n: NodeSummary): string {
    if (n.worst_severity === 'critical') return 'tone-bad';
    return n.unacknowledged > 0 ? 'tone-warn' : 'tone-good';
  }

  trackByIndex(index: number): number { return index; }
  trackByLabel(_: number, item: { label: string }): string { return item.label; }
}
