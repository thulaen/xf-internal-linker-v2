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
  NativeModuleStatus,
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
import { forkJoin, Subject, catchError, of, takeUntil, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { RealtimeService } from '../core/services/realtime.service';
import { ScrollAttentionService } from '../core/services/scroll-attention.service';
import { TopicUpdate } from '../core/services/realtime.types';
import { environment } from '../../environments/environment';

// ────────────────────────────────────────────────────────────────────
// Phase GT Step 11 — Error Log section types
// ────────────────────────────────────────────────────────────────────

/**
 * A fingerprint-grouped bucket of errors rendered as a single row in the
 * Error Log. The representative row carries the display fields; totalCount
 * is the sum of `occurrence_count` across the bucket so the UI can show
 * an accurate multiplier badge without scanning the list every render.
 */
interface ErrorGroup {
  fingerprint: string;
  representative: ErrorLogEntry;
  totalCount: number;
}

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
    const previousIds = new Set(this.errors.map((e) => e.id));
    const nextUnack = next.filter((e) => !e.acknowledged);
    const nextAck = next.filter((e) => e.acknowledged);

    this.errors = nextUnack;
    this.acknowledgedErrors = nextAck;

    // Find rows that are new in this snapshot AND critical/high.
    const arrivals = nextUnack.filter(
      (e) =>
        !previousIds.has(e.id) &&
        (e.severity === 'critical' || e.severity === 'high'),
    );
    if (arrivals.length === 0) return;

    // Pulse the most recent critical arrival (or the most recent high if
    // no critical is present). Single pulse — Scroll-to-Attention dedups
    // via its built-in dismiss-before-draw pattern.
    const priorityTarget =
      arrivals.find((e) => e.severity === 'critical') ?? arrivals[0];
    // Defer one tick so Angular has rendered the new <article id="error-{id}">
    // by the time we call scrollIntoView.
    window.setTimeout(() => {
      this.scrollAttention.drawTo(`#error-${priorityTarget.id}`, {
        priority: 'urgent',
        announce: `New ${priorityTarget.severity} error in ${priorityTarget.job_type}.`,
      });
    }, 0);
  }

  loadData(): void {
    this.loading = true;
    // Phase GT Step 11 — each of the four new endpoints is wrapped in
    // catchError → `of(<safe default>)` so a single failing endpoint cannot
    // block the whole page. This is important because runtime-context
    // transiently returns 500 during worker restarts, and we'd rather show
    // a page without the GPU strip than a blank Diagnostics screen.
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
        this.runtimeLaneCards = this.buildRuntimeLaneCards(data.services);
        this.runtimeExecutionCards = this.buildRuntimeExecutionCards(data.services);
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
    switch (update.event) {
      case 'service.status.created':
      case 'service.status.updated':
        this.upsertService(update.payload as ServiceStatus);
        break;
      case 'service.status.deleted':
        this.removeService((update.payload as { id: number }).id);
        break;
      case 'conflict.created':
      case 'conflict.updated':
        this.upsertConflict(update.payload as SystemConflict);
        break;
      case 'conflict.deleted':
        this.removeConflict((update.payload as { id: number }).id);
        break;
      // Unknown events are ignored intentionally — future-proof against new
      // event names being added to the signals.py emitter.
    }
  }

  private upsertService(next: ServiceStatus): void {
    const prev = this.services.find((s) => s.id === next.id);
    const wasHealthy = prev ? prev.state === 'healthy' : true;
    const nowFailed = next.state === 'failed';

    if (prev) {
      this.services = this.services.map((s) => (s.id === next.id ? next : s));
    } else {
      this.services = [...this.services, next];
    }

    // Rebuild derived cards so tiles reflect the new state instantly.
    this.runtimeLaneCards = this.buildRuntimeLaneCards(this.services);
    this.runtimeExecutionCards = this.buildRuntimeExecutionCards(this.services);

    // Pulse-scroll into view when a service newly failed — this is why the
    // cross-cutting scroll-to-attention service exists (Phase GB / Gap 148).
    if (wasHealthy && nowFailed) {
      this.scrollAttention.drawTo(`#service-${next.id}`, {
        priority: 'urgent',
        announce: `${next.service_name} just failed.`,
      });
    }
  }

  private removeService(id: number): void {
    this.services = this.services.filter((s) => s.id !== id);
    this.runtimeLaneCards = this.buildRuntimeLaneCards(this.services);
    this.runtimeExecutionCards = this.buildRuntimeExecutionCards(this.services);
  }

  private upsertConflict(next: SystemConflict): void {
    const prev = this.conflicts.find((c) => c.id === next.id);
    const wasResolved = prev ? prev.resolved : true;
    const nowUnresolved = !next.resolved;

    if (prev) {
      this.conflicts = this.conflicts.map((c) => (c.id === next.id ? next : c));
    } else {
      this.conflicts = [...this.conflicts, next];
    }

    if (wasResolved && nowUnresolved && (next.severity === 'high' || next.severity === 'critical')) {
      this.scrollAttention.drawTo(`#conflict-${next.id}`, {
        priority: 'urgent',
        announce: `New ${next.severity} conflict: ${next.title}.`,
      });
    }
  }

  private removeConflict(id: number): void {
    this.conflicts = this.conflicts.filter((c) => c.id !== id);
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
    const filtered = this.filterNodeId
      ? this.errors.filter((e) => e.node_id === this.filterNodeId)
      : this.errors;

    const buckets = new Map<string, ErrorLogEntry[]>();
    for (const e of filtered) {
      const key = e.fingerprint ?? `unique-${e.id}`;
      const existing = buckets.get(key);
      if (existing) {
        existing.push(e);
      } else {
        buckets.set(key, [e]);
      }
    }

    const result: ErrorGroup[] = [];
    buckets.forEach((entries, fingerprint) => {
      // Sum occurrence_count across bucket, defaulting to entries.length
      // when a row is missing the field (old snapshots).
      const totalCount = entries.reduce(
        (sum, e) => sum + (e.occurrence_count ?? 1),
        0,
      );
      result.push({
        fingerprint,
        representative: entries[0],
        totalCount,
      });
    });
    return result;
  }

  /** Unique node ids seen in the current error list — powers the filter
   *  chip bar. Returned in first-seen order so the chip layout is stable
   *  across re-renders. */
  uniqueNodes(): string[] {
    const seen: string[] = [];
    const set = new Set<string>();
    for (const e of this.errors) {
      const id = e.node_id;
      if (id && !set.has(id)) {
        set.add(id);
        seen.push(id);
      }
    }
    return seen;
  }

  /** Peak value in a 7-day sparkline — used to scale bar heights. Floor
   *  of 1 so the bars never `Infinity / 0`. */
  maxTrendCount(trend: { count: number }[] | undefined): number {
    if (!trend || trend.length === 0) return 1;
    return Math.max(1, ...trend.map((t) => t.count));
  }

  /** Other errors within the ±5-minute window the backend pre-computed.
   *  Constrained to the current unack list so acknowledged rows don't
   *  appear as "related" noise. */
  relatedErrors(e: ErrorLogEntry): ErrorLogEntry[] {
    const ids = new Set(e.related_error_ids ?? []);
    if (ids.size === 0) return [];
    return this.errors.filter((x) => ids.has(x.id));
  }

  /** Text-only ISO date rendered in sparkline tooltip. Split so the HTML
   *  template stays lean and the slice matches exactly one bar. */
  trendLabel(trend: { date: string; count: number }[] | undefined): string {
    if (!trend || trend.length === 0) return '';
    return `Last 7 days: total ${trend.reduce((s, t) => s + t.count, 0)}`;
  }

  trackGroupFingerprint(_index: number, group: ErrorGroup): string {
    return group.fingerprint;
  }

  trackErrorId(_index: number, error: ErrorLogEntry): number {
    return error.id;
  }

  trackNodeId(_index: number, node: NodeSummary): string {
    return node.node_id;
  }

  trackTrendDate(_index: number, point: { date: string }): string {
    return point.date;
  }

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

  /** Only one details panel open at a time (see `expandedErrorId`). */
  toggleExpand(id: number): void {
    this.expandedErrorId = this.expandedErrorId === id ? null : id;
  }

  /** Click-to-filter on a node card in the GT-G13 strip. Clicking the same
   *  card toggles the filter off. */
  toggleNodeFilter(nodeId: string | null): void {
    this.filterNodeId = this.filterNodeId === nodeId ? null : nodeId;
  }

  /** Open the Django Admin in a new tab. `noopener` is mandatory per the
   *  privacy-protection rules (no window.opener leakage). */
  openDjangoAdmin(): void {
    window.open(this.adminUrl, '_blank', 'noopener,noreferrer');
  }

  /**
   * GT-G2 — build an AI-ready prompt for the error and copy to clipboard.
   * The resulting text is self-contained: an engineer can paste it into
   * Claude/Codex/ChatGPT with no additional context. Runtime snapshot
   * and traceback (when present) are inlined so the LLM sees the full
   * picture without leaking secrets beyond what's already in the error.
   */
  copyForAI(e: ErrorLogEntry): void {
    const ctx = e.runtime_context ?? {};
    const lines: string[] = [];
    lines.push('## Error Report');
    lines.push(`**Job:** ${e.job_type} · ${e.step}`);
    lines.push(`**Node:** ${e.node_id ?? 'unknown'} (${e.node_role ?? 'unknown'})`);
    lines.push(`**Severity:** ${e.severity ?? 'medium'}`);
    lines.push(`**What happened:** ${e.error_message}`);
    if (e.why) lines.push(`**Why:** ${e.why}`);
    if (e.how_to_fix) lines.push(`**Suggested fix:** ${e.how_to_fix}`);
    lines.push(
      `**Runtime at time of error:** GPU=${ctx.gpu_available ? 'yes' : 'no'} · ` +
        `embedding=${ctx.embedding_model ?? 'unknown'} · ` +
        `spaCy=${ctx.spacy_model ?? 'missing'} · ` +
        `python=${ctx.python_version ?? 'unknown'}`,
    );
    if (e.raw_exception) {
      lines.push('', '**Traceback:**', '```', e.raw_exception, '```');
    }
    if (e.glitchtip_url) {
      lines.push('', `**GlitchTip:** ${e.glitchtip_url}`);
    }
    const prompt = lines.join('\n');

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

  /** Is the error row actionable via Rerun? Centralised so the template
   *  stays readable and new job types are trivial to add. */
  canRerun(e: ErrorLogEntry): boolean {
    return ['pipeline', 'sync', 'import'].includes(e.job_type);
  }

  /** CSS class for the severity stripe on the left edge of each row. */
  severityClass(e: ErrorLogEntry): string {
    return `severity-${e.severity ?? 'medium'}`;
  }

  /** Tone class for the node card — green when clean, yellow when there
   *  are unacknowledged errors but nothing critical, red when any critical
   *  entry exists on that node. */
  nodeToneClass(n: NodeSummary): string {
    if (n.worst_severity === 'critical') return 'tone-bad';
    if (n.unacknowledged > 0) return 'tone-warn';
    return 'tone-good';
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
