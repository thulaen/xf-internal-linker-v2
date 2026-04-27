import { ChangeDetectionStrategy, Component, OnInit, OnDestroy, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDividerModule } from '@angular/material/divider';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatTabsModule } from '@angular/material/tabs';
import { MatStepperModule } from '@angular/material/stepper';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { HttpClient } from '@angular/common/http';
import { catchError, of, Subject, Subscription, takeUntil, timer, switchMap } from 'rxjs';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { SyncService, SyncJob } from './sync.service';
import { JobDetailDialogComponent, JobDetailDialogResult } from './job-detail-dialog.component';
import { HealthBannerComponent } from '../shared/health-banner/health-banner.component';
import { EmptyStateComponent } from '../shared/empty-state/empty-state.component';
import { SystemMetricsComponent } from '../dashboard/system-metrics/system-metrics.component';
import { SchedulingPolicyCardComponent } from './scheduling-policy-card/scheduling-policy-card.component';
import { RealtimeService } from '../core/services/realtime.service';
import { TopicUpdate } from '../core/services/realtime.types';
import { AuthService } from '../core/services/auth.service';

type ImportState = 'idle' | 'uploading' | 'running' | 'paused' | 'completed' | 'failed';
type JobSource = 'api' | 'wp' | 'jsonl';

/**
 * View shape per import source — only the bits the template renders.
 *
 * Renamed from `SourceJobState` and trimmed of `ws` / `pollingSub`,
 * which live in parallel private Records. That separation means a
 * WebSocket reconnect or polling-fallback toggle never invalidates a
 * signal, so OnPush change detection only re-renders when an actual
 * user-visible field (state, progress, message) changes.
 */
interface JobView {
  state: ImportState;
  jobId: string | null;
  ingestProgress: number;
  mlProgress: number;
  spacyProgress: number;
  embeddingProgress: number;
  progressMessage: string;
  errorMessage: string;
}

@Component({
  selector: 'app-jobs',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatFormFieldModule,
    MatDividerModule,
    MatTableModule,
    MatTooltipModule,
    MatDialogModule,
    MatSnackBarModule,
    MatTabsModule,
    MatStepperModule,
    MatChipsModule,
    HealthBannerComponent,
    EmptyStateComponent,
    SystemMetricsComponent,
    SchedulingPolicyCardComponent,
  ],
  templateUrl: './jobs.component.html',
  styleUrls: ['./jobs.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JobsComponent implements OnInit, OnDestroy {
  // Plain mutable fields back two-way bindings on form controls:
  //   importMode → mat-select [(ngModel)]
  //   selectedTab → mat-tab-group [(selectedIndex)]
  // Both directives need an lvalue, not a signal getter. Their
  // (change)/(selectedIndexChange) handlers fire on the host so OnPush
  // still re-evaluates downstream bindings after each user action.
  importMode = 'full';
  selectedTab = 0;

  // Render-affecting state in signals so OnPush picks up every mutation.
  readonly selectedFile = signal<File | null>(null);
  readonly isDragOver = signal(false);
  readonly jsonlExpanded = signal(false);

  readonly sourceStatus = signal<{ api: boolean; wp: boolean }>({ api: false, wp: false });
  readonly syncJobs = signal<SyncJob[]>([]);

  // Per-source job state. ONE signal of a Record keyed by source; the
  // template's `getJob('api'|'wp'|'jsonl')` accessor reads from it so
  // every per-source binding is automatically a tracked signal consumer.
  readonly jobs = signal<Record<JobSource, JobView>>({
    api: this.emptyJobView(),
    wp: this.emptyJobView(),
    jsonl: this.emptyJobView(),
  });

  // Internal-only resource handles. NOT signals — flipping a WebSocket
  // ref or a Subscription handle should never trigger UI re-render. The
  // user-visible consequences (state transitions, progress %) flow
  // through `jobs` instead.
  private wsRefs: Record<JobSource, WebSocket | null> = { api: null, wp: null, jsonl: null };
  private pollingRefs: Record<JobSource, Subscription | null> = { api: null, wp: null, jsonl: null };

  // Queue + Quarantine (Stage 5)
  readonly queueItems = signal<unknown[]>([]);
  readonly quarantineItems = signal<unknown[]>([]);
  readonly activeLocks = signal<Record<string, string | null>>({});

  // Static config — `readonly` to make immutability explicit.
  readonly displayedColumns: string[] = ['created_at', 'source', 'mode', 'status', 'progress', 'duration', 'success_rate', 'actions'];

  readonly modes = [
    { value: 'full',   label: 'Full import',  hint: 'Downloads everything needed for accurate suggestions (recommended first time)' },
    { value: 'titles', label: 'Titles only',  hint: 'Fast refresh — only updates page titles and metadata'  },
    { value: 'quick',  label: 'Quick check',  hint: 'Fastest — only checks for new and removed pages'      },
  ];

  readonly sources: readonly JobSource[] = ['api', 'wp', 'jsonl'];

  // Derived view state. Recomputes when its signal dependencies change.
  readonly anyRunning = computed(() =>
    Object.values(this.jobs()).some(j => j.state === 'running' || j.state === 'uploading'),
  );

  readonly canSyncAll = computed(() => {
    const status = this.sourceStatus();
    const j = this.jobs();
    return (status.api && j.api.state === 'idle') || (status.wp && j.wp.state === 'idle');
  });

  private syncService = inject(SyncService);
  private http = inject(HttpClient);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private realtime = inject(RealtimeService);
  private visibilityGate = inject(VisibilityGateService);
  private auth = inject(AuthService);
  private destroy$ = new Subject<void>();

  // ── State helpers ────────────────────────────────────────────────────

  private emptyJobView(): JobView {
    return {
      state: 'idle', jobId: null,
      ingestProgress: 0, mlProgress: 0,
      spacyProgress: 0, embeddingProgress: 0,
      progressMessage: '', errorMessage: '',
    };
  }

  /** Snapshot read for one source. Called from template bindings; the
   *  signal read inside is tracked by Angular's CD instrumentation, so
   *  per-source bindings re-evaluate when `jobs` updates. */
  getJob(source: JobSource): JobView {
    return this.jobs()[source];
  }

  /** Shallow-merge a per-source patch. Atomic single signal update —
   *  multiple field changes in one render cycle (e.g. a WS progress
   *  message updating four progress percentages plus a status message)
   *  go through one mutation, not five. */
  private patchJob(source: JobSource, patch: Partial<JobView>): void {
    this.jobs.update(j => ({ ...j, [source]: { ...j[source], ...patch } }));
  }

  /** Replace a per-source view wholesale (used by resetJob). */
  private setJob(source: JobSource, view: JobView): void {
    this.jobs.update(j => ({ ...j, [source]: view }));
  }

  // ── Template-facing getters & helpers ────────────────────────────────

  getLastSync(source: JobSource): SyncJob | null {
    return this.syncJobs()
      .filter(j => j.source === source && j.status === 'completed')
      .sort((a, b) =>
        new Date(b.completed_at ?? b.created_at).getTime() -
        new Date(a.completed_at ?? a.created_at).getTime()
      )[0] ?? null;
  }

  getDuration(job: SyncJob): string {
    if (!job.started_at || !job.completed_at) return '';
    const start = new Date(job.started_at).getTime();
    const end = new Date(job.completed_at).getTime();
    const diff = Math.max(0, end - start);

    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);

    if (minutes > 0) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
  }

  getSuccessRate(job: SyncJob): string {
    // If we have total items in the future, use them.
    // Currently, for ML phase we can show completed/queued.
    if (job.ml_items_queued > 0) {
      const rate = Math.round((job.ml_items_completed / job.ml_items_queued) * 100);
      return `${rate}%`;
    }
    // For ingest, we just show 100% if completed and there are items.
    return job.status === 'completed' ? '100%' : '0%';
  }

  // A job is "stuck" if it has been running for more than 2 hours without completing.
  isStuck(job: SyncJob): boolean {
    if (job.status !== 'running' || !job.started_at) return false;
    const ageMs = Date.now() - new Date(job.started_at).getTime();
    return ageMs > 2 * 60 * 60 * 1000;
  }

  getStatusTooltip(job: SyncJob): string {
    if (this.isStuck(job)) return 'Job appears stuck — will be cleaned up automatically overnight';
    if (job.is_resumable && job.checkpoint_stage) {
      return `Resumable from ${job.checkpoint_stage} checkpoint`;
    }
    if (job.status === 'failed' && job.error_message) return job.error_message;
    return job.status;
  }

  canResumeJob(job: SyncJob): boolean {
    return job.is_resumable
      && !!job.checkpoint_stage
      && ['paused', 'failed', 'cancelled'].includes(job.status);
  }

  showJobDetail(job: SyncJob): void {
    const ref = this.dialog.open<
      JobDetailDialogComponent,
      { job: SyncJob },
      JobDetailDialogResult | undefined
    >(JobDetailDialogComponent, {
      width: '480px',
      data: { job },
    });

    ref.afterClosed()
      .pipe(takeUntil(this.destroy$))
      .subscribe((result) => {
        if (result?.action === 'retry' && result.source && result.mode) {
          this.syncService.triggerApiSync(result.source, result.mode)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
              next: () => {
                this.snack.open('Retry started — check progress above', 'Dismiss', { duration: 5000 });
                this.loadHistory();
              },
              error: () => {
                this.snack.open('Failed to retry job', 'Dismiss', { duration: 4000 });
              },
            });
        } else if (result?.action === 'resume' && result.jobId) {
          this.resumeSyncJob(result.jobId);
        }
      });
  }

  ngOnInit(): void {
    this.loadHistory();
    this.loadSourceStatus();
    this.loadQueue();
    this.loadQuarantine();

    // Phase R1.3 — live updates from `jobs.history` topic. Every SyncJob
    // save fans out instantly; the historyInterval below drops to a
    // 2-minute defensive fallback (if the WS drops, state still recovers).
    this.realtime
      .subscribeTopic('jobs.history')
      .pipe(takeUntil(this.destroy$))
      .subscribe((update: TopicUpdate) => this.handleJobsRealtimeUpdate(update));

    // 2-minute defensive fallback for `jobs.history` WebSocket drops.
    // Gated by `VisibilityGateService` — hidden tabs / signed-out
    // sessions skip the poll. See docs/PERFORMANCE.md §13. The legacy
    // `historyInterval` setInterval handle is no longer needed; the
    // RxJS stream is cleaned up by `takeUntil(this.destroy$)`.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(120_000, 120_000).pipe(switchMap(() => of(null))),
      )
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => this.loadHistory());
  }

  private handleJobsRealtimeUpdate(update: TopicUpdate): void {
    if (update.event === 'job.deleted') {
      const id = (update.payload as { job_id: string }).job_id;
      this.syncJobs.update(arr => arr.filter(j => j.job_id !== id));
      return;
    }
    if (update.event === 'job.created' || update.event === 'job.updated') {
      const next = update.payload as SyncJob;
      // Single atomic update — read-modify-write happens inside the
      // signal updater so two emissions in quick succession can't race
      // and lose each other's state. Mirrors the webhook-log fix.
      this.syncJobs.update(arr => {
        const idx = arr.findIndex(j => j.job_id === next.job_id);
        if (idx >= 0) {
          return arr.map(j => (j.job_id === next.job_id ? next : j));
        }
        return [next, ...arr];
      });
    }
  }

  loadQueue(): void {
    this.http.get<{ items: unknown[]; locks: Record<string, string | null> }>('/api/jobs/queue/')
      .pipe(catchError(() => of({ items: [], locks: {} })), takeUntil(this.destroy$))
      .subscribe(data => {
        this.queueItems.set(data.items);
        this.activeLocks.set(data.locks);
      });
  }

  loadQuarantine(): void {
    this.http.get<unknown[]>('/api/jobs/quarantine/')
      .pipe(catchError(() => of([])), takeUntil(this.destroy$))
      .subscribe(items => this.quarantineItems.set(items));
  }

  /**
   * Graceful pause request for a running sync job (plan item 27).
   * Worker will stop at the next safe checkpoint boundary.
   */
  pauseSyncJob(jobId: string): void {
    this.syncService.pauseJob(jobId)
      .pipe(catchError(() => of(null)), takeUntil(this.destroy$))
      .subscribe((res: { status?: string; message?: string } | null) => {
        if (res && res.status === 'paused') {
          this.snack.open(
            res.message || 'Pause requested. Worker will stop at the next safe checkpoint.',
            'OK',
            { duration: 4000 },
          );
          this.loadQueue();
          this.loadHistory();
        } else {
          this.snack.open('Could not pause this job.', 'OK', { duration: 4000 });
        }
      });
  }

  /**
   * Resume a paused sync job from its saved checkpoint (plan item 27).
   */
  resumeSyncJob(jobId: string): void {
    this.syncService.resumeJob(jobId)
      .pipe(catchError(() => of(null)), takeUntil(this.destroy$))
      .subscribe((res: { status?: string; message?: string } | null) => {
        if (res && res.status === 'pending') {
          this.snack.open(
            res.message || 'Resume queued. The worker will pick up from the saved checkpoint.',
            'OK',
            { duration: 4000 },
          );
          this.loadQueue();
          this.loadHistory();
        } else {
          this.snack.open('Could not resume this job.', 'OK', { duration: 4000 });
        }
      });
  }

  /**
   * Open the dry-run preview dialog for a source (plan item 25).
   * Never starts the real sync itself; if the user picks "Run for real"
   * in the dialog, we dispatch to startSourceSync on close.
   */
  async previewSync(source: 'api' | 'wp'): Promise<void> {
    const { SyncPreviewDialogComponent } = await import(
      './sync-preview-dialog/sync-preview-dialog.component'
    );
    const ref = this.dialog.open(SyncPreviewDialogComponent, {
      data: { source, mode: this.importMode },
      width: '560px',
      maxWidth: '92vw',
      autoFocus: 'first-tabbable',
      restoreFocus: true,
    });
    ref.afterClosed()
      .pipe(takeUntil(this.destroy$))
      .subscribe((decision) => {
        if (decision === 'run') {
          this.startSourceSync(source);
        }
      });
  }

  async launchQuarantineRunbook(item: { fix_available?: string; run_id?: string; related_object_type?: string }): Promise<void> {
    const [{ RunbookDialogComponent }, { RUNBOOK_LIBRARY }] = await Promise.all([
      import('../shared/runbooks/runbook-dialog/runbook-dialog.component'),
      import('../shared/runbooks/runbook-library'),
    ]);
    const id = item?.fix_available || 'reset-quarantined-job';
    const runbook = RUNBOOK_LIBRARY.find((r) => r.id === id) ?? RUNBOOK_LIBRARY.find((r) => r.id === 'reset-quarantined-job');
    if (!runbook) return;
    // Pass run_id (and related_object_type) as context so the backend runbook
    // endpoint gets the args it needs (e.g. reset-quarantined-job requires run_id).
    this.dialog.open(RunbookDialogComponent, {
      data: {
        runbook,
        context: {
          run_id: item?.run_id,
          related_object_type: item?.related_object_type ?? 'pipeline_run',
        },
      },
      width: '520px',
      maxWidth: '92vw',
      autoFocus: 'first-tabbable',
      restoreFocus: true,
    });
  }

  loadSourceStatus(): void {
    this.syncService.getSourceStatus()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (s) => {
          if (s && typeof s === 'object') {
            this.sourceStatus.set(s);
          }
        },
        error: () => {
          // Keep current state on error
        },
      });
  }

  loadHistory(): void {
    this.syncService.getJobs()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (jobs) => {
          // Ensure we only bind to arrays to avoid NG02200 crash
          this.syncJobs.set(Array.isArray(jobs) ? jobs : []);
        },
        error: (err) => {
          this.syncJobs.set([]);
          console.error('Failed to load job history', err);
        },
      });
  }

  syncAllWpxf(): void {
    const status = this.sourceStatus();
    const j = this.jobs();
    if (status.api && j.api.state === 'idle') this.startSourceSync('api');
    if (status.wp  && j.wp.state  === 'idle') this.startSourceSync('wp');
  }

  startSourceSync(source: 'api' | 'wp'): void {
    if (this.getJob(source).state !== 'idle') return;

    this.patchJob(source, {
      state: 'running',
      ingestProgress: 0,
      mlProgress: 0,
      progressMessage: `Requesting ${source === 'api' ? 'XenForo' : 'WordPress'} sync…`,
      errorMessage: '',
    });

    this.syncService.triggerApiSync(source, this.importMode)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res) => {
          this.patchJob(source, {
            jobId: res.job_id,
            progressMessage: 'Sync scheduled — connecting…',
          });
          this.connectWebSocketForSource(source, res.job_id);
          this.loadHistory();
        },
        error: (err) => {
          this.patchJob(source, {
            state: 'failed',
            errorMessage: err.error?.error ?? 'Sync request failed.',
          });
        },
      });
  }

  startJsonlImport(): void {
    const file = this.selectedFile();
    if (!file) return;
    if (this.getJob('jsonl').state !== 'idle') return;

    this.patchJob('jsonl', {
      state: 'uploading',
      ingestProgress: 0,
      mlProgress: 0,
      progressMessage: 'Uploading file…',
      errorMessage: '',
    });

    this.syncService.uploadFile(file, this.importMode)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res) => {
          this.patchJob('jsonl', {
            jobId: res.job_id,
            state: 'running',
            progressMessage: 'Import scheduled — connecting…',
          });
          this.connectWebSocketForSource('jsonl', res.job_id);
          this.loadHistory();
        },
        error: (err) => {
          this.patchJob('jsonl', {
            state: 'failed',
            errorMessage: err.error?.error ?? 'Upload failed.',
          });
        },
      });
  }

  resetJob(source: JobSource): void {
    this.wsRefs[source]?.close();
    this.wsRefs[source] = null;
    this.pollingRefs[source]?.unsubscribe();
    this.pollingRefs[source] = null;
    this.setJob(source, this.emptyJobView());
    if (source === 'jsonl') {
      this.selectedFile.set(null);
      this.jsonlExpanded.set(false);
    }
  }

  private connectWebSocketForSource(source: JobSource, jobId: string): void {
    this.wsRefs[source]?.close();

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const base = `${proto}://${location.host}/ws/jobs/${jobId}/`;
    const token = this.auth.getToken();
    const url = token ? `${base}?token=${encodeURIComponent(token)}` : base;
    const ws = new WebSocket(url);
    this.wsRefs[source] = ws;

    ws.onmessage = (event) => {
      let data: { type?: string; state?: string; message?: string; error?: string;
        ingest_progress?: number; ml_progress?: number; spacy_progress?: number;
        embedding_progress?: number; progress?: number };
      try {
        data = JSON.parse(event.data);
      } catch {
        console.warn('Jobs WebSocket: malformed message', event.data);
        return;
      }

      if (data.type === 'connection.established') {
        this.patchJob(source, { progressMessage: 'Connected. Waiting for progress…' });
        return;
      }

      if (data.type === 'job.progress') {
        const patch: Partial<JobView> = {
          ingestProgress: Math.round((data.ingest_progress ?? data.progress ?? 0) * 100),
          mlProgress: Math.round((data.ml_progress ?? 0) * 100),
          spacyProgress: Math.round((data.spacy_progress ?? 0) * 100),
          embeddingProgress: Math.round((data.embedding_progress ?? 0) * 100),
          progressMessage: data.message ?? '',
        };

        if (data.state === 'completed') {
          patch.state = 'completed';
          patch.ingestProgress = 100;
          patch.mlProgress = 100;
          patch.spacyProgress = 100;
          patch.embeddingProgress = 100;
        } else if (data.state === 'failed') {
          patch.state = 'failed';
          patch.errorMessage = data.error ?? 'Import failed.';
        } else if (data.state === 'paused') {
          patch.state = 'paused';
        }

        this.patchJob(source, patch);

        if (data.state === 'completed' || data.state === 'failed' || data.state === 'paused') {
          ws.close();
          this.clearPolling(source);
          this.loadHistory();
        }
      }
    };

    ws.onerror = () => { if (this.getJob(source).state === 'running') this.startPollingForSource(source, jobId); };
    ws.onclose = () => { if (this.getJob(source).state === 'running') this.startPollingForSource(source, jobId); };
  }

  private startPollingForSource(source: JobSource, jobId: string): void {
    if (this.pollingRefs[source]) return;
    // Polling pauses automatically while the tab is hidden or the user
    // is signed out. See docs/PERFORMANCE.md §13.
    this.pollingRefs[source] = this.visibilityGate
      .whileLoggedInAndVisible(() => timer(3000, 3000))
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        this.syncService.getJob(jobId)
          .pipe(takeUntil(this.destroy$))
          .subscribe({
            next: (j) => {
              const patch: Partial<JobView> = {
                ingestProgress: Math.round((j.ingest_progress ?? j.progress ?? 0) * 100),
                mlProgress: Math.round((j.ml_progress ?? 0) * 100),
                spacyProgress: Math.round((j.spacy_progress ?? 0) * 100),
                embeddingProgress: Math.round((j.embedding_progress ?? 0) * 100),
                progressMessage: j.message ?? '',
              };
              if (j.status === 'completed') {
                patch.state = 'completed';
              } else if (j.status === 'failed') {
                patch.state = 'failed';
                patch.errorMessage = j.error_message ?? 'Import failed.';
              } else if (j.status === 'paused') {
                patch.state = 'paused';
              }
              this.patchJob(source, patch);

              if (j.status === 'completed' || j.status === 'failed' || j.status === 'paused') {
                this.clearPolling(source);
                this.loadHistory();
              }
            },
            // Outer poll keeps ticking — surface the per-fetch failure so
            // the dev tools network tab + console line up when the backend
            // is hiccupping. Was an empty `() => {}` swallow.
            error: (err) => console.warn(`job poll fetch failed (${source})`, err),
          });
      });
  }

  private clearPolling(source: JobSource): void {
    this.pollingRefs[source]?.unsubscribe();
    this.pollingRefs[source] = null;
  }

  // ── Drag and drop ───────────────────────────────────────────────

  onDragOver(event: DragEvent): void { event.preventDefault(); this.isDragOver.set(true); }
  onDragLeave(): void { this.isDragOver.set(false); }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    const file = event.dataTransfer?.files[0];
    if (file) this.setFile(file);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) this.setFile(file);
    input.value = '';
  }

  private setFile(file: File): void {
    if (!file.name.toLowerCase().endsWith('.jsonl')) {
      this.patchJob('jsonl', { errorMessage: 'Only .jsonl files are accepted.' });
      return;
    }
    this.patchJob('jsonl', { errorMessage: '' });
    this.selectedFile.set(file);
  }

  /** Template-side cancel button — collapses the file selection and the
   *  expanded dropzone in one transition. Called from the template; the
   *  previous inline `(click)="selectedFile = null; jsonlExpanded = false"`
   *  doesn't compile against signals. */
  cancelFileSelection(): void {
    this.selectedFile.set(null);
    this.jsonlExpanded.set(false);
  }

  /** Template-side toggle for the dropzone expand/collapse button. */
  toggleJsonlExpanded(): void {
    this.jsonlExpanded.update(v => !v);
  }

  // ── History helpers ─────────────────────────────────────────────

  getStatusIcon(status: string): string {
    switch (status) {
      case 'completed': return 'check_circle';
      case 'failed':    return 'error';
      case 'running':   return 'sync';
      case 'pending':   return 'schedule';
      case 'paused':    return 'pause_circle';
      case 'cancelled': return 'cancel';
      default:          return 'help_outline';
    }
  }

  getStatusClass(status: string): string {
    return `status-${status}`;
  }

  ngOnDestroy(): void {
    for (const source of this.sources) {
      this.wsRefs[source]?.close();
      this.clearPolling(source);
    }
    this.destroy$.next();
    this.destroy$.complete();
  }
}
