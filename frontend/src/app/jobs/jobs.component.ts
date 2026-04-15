import { Component, OnInit, OnDestroy, inject } from '@angular/core';
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
import { catchError, of } from 'rxjs';
import { SyncService, SyncJob } from './sync.service';
import { JobDetailDialogComponent, JobDetailDialogResult } from './job-detail-dialog.component';
import { HealthBannerComponent } from '../shared/health-banner/health-banner.component';
import { EmptyStateComponent } from '../shared/empty-state/empty-state.component';
import { SystemMetricsComponent } from '../dashboard/system-metrics/system-metrics.component';
import { SchedulingPolicyCardComponent } from './scheduling-policy-card/scheduling-policy-card.component';

type ImportState = 'idle' | 'uploading' | 'running' | 'paused' | 'completed' | 'failed';

interface SourceJobState {
  state: ImportState;
  jobId: string | null;
  ingestProgress: number;
  mlProgress: number;
  spacyProgress: number;
  embeddingProgress: number;
  progressMessage: string;
  errorMessage: string;
  ws: WebSocket | null;
  pollingInterval: ReturnType<typeof setInterval> | null;
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
})
export class JobsComponent implements OnInit, OnDestroy {
  importMode = 'full';
  selectedFile: File | null = null;
  isDragOver = false;
  jsonlExpanded = false;

  sourceStatus: { api: boolean; wp: boolean } = { api: false, wp: false };
  syncJobs: SyncJob[] = [];
  displayedColumns: string[] = ['created_at', 'source', 'mode', 'status', 'progress', 'duration', 'success_rate', 'actions'];

  private historyInterval: ReturnType<typeof setInterval> | null = null;

  jobs: Record<'api' | 'wp' | 'jsonl', SourceJobState> = {
    api:   this.emptyJob(),
    wp:    this.emptyJob(),
    jsonl: this.emptyJob(),
  };

  private syncService = inject(SyncService);
  private http = inject(HttpClient);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);

  // Queue + Quarantine (Stage 5)
  queueItems: any[] = [];
  quarantineItems: any[] = [];
  activeLocks: Record<string, string | null> = {};
  selectedTab = 0;

  readonly modes = [
    { value: 'full',   label: 'Full import',  hint: 'Downloads everything needed for accurate suggestions (recommended first time)' },
    { value: 'titles', label: 'Titles only',  hint: 'Fast refresh — only updates page titles and metadata'  },
    { value: 'quick',  label: 'Quick check',  hint: 'Fastest — only checks for new and removed pages'      },
  ];

  readonly sources: ('api' | 'wp' | 'jsonl')[] = ['api', 'wp', 'jsonl'];

  private emptyJob(): SourceJobState {
    return {
      state: 'idle', jobId: null,
      ingestProgress: 0, mlProgress: 0,
      spacyProgress: 0, embeddingProgress: 0,
      progressMessage: '', errorMessage: '',
      ws: null, pollingInterval: null,
    };
  }

  get anyRunning(): boolean {
    return Object.values(this.jobs).some(j => j.state === 'running' || j.state === 'uploading');
  }

  get canSyncAll(): boolean {
    return (this.sourceStatus.api && this.jobs['api'].state === 'idle') ||
           (this.sourceStatus.wp  && this.jobs['wp'].state  === 'idle');
  }

  getJob(source: 'api' | 'wp' | 'jsonl'): SourceJobState {
    return this.jobs[source];
  }

  getLastSync(source: 'api' | 'wp' | 'jsonl'): SyncJob | null {
    return this.syncJobs
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

    ref.afterClosed().subscribe((result) => {
      if (result?.action === 'retry' && result.source && result.mode) {
        this.syncService.triggerApiSync(result.source, result.mode).subscribe({
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
    // Refresh the history table every 30 seconds so status changes are visible.
    this.historyInterval = setInterval(() => this.loadHistory(), 30_000);
  }

  loadQueue(): void {
    this.http.get<{ items: any[]; locks: Record<string, string | null> }>('/api/jobs/queue/')
      .pipe(catchError(() => of({ items: [], locks: {} })))
      .subscribe(data => {
        this.queueItems = data.items;
        this.activeLocks = data.locks;
      });
  }

  loadQuarantine(): void {
    this.http.get<any[]>('/api/jobs/quarantine/')
      .pipe(catchError(() => of([])))
      .subscribe(items => this.quarantineItems = items);
  }

  /**
   * Open the RunbookDialog matching the quarantine record's fix_available id
   * (plan item 16 / 17 integration). If the runbook isn't in the library we
   * fall back to the generic reset-quarantined-job entry.
   */
  /**
   * Graceful pause request for a running sync job (plan item 27).
   * Worker will stop at the next safe checkpoint boundary.
   */
  pauseSyncJob(jobId: string): void {
    this.syncService.pauseJob(jobId)
      .pipe(catchError(() => of(null)))
      .subscribe((res: any) => {
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
      .pipe(catchError(() => of(null)))
      .subscribe((res: any) => {
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
    ref.afterClosed().subscribe((decision) => {
      if (decision === 'run') {
        this.startSourceSync(source);
      }
    });
  }

  async launchQuarantineRunbook(item: any): Promise<void> {
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
    this.syncService.getSourceStatus().subscribe({
      next: (s) => { 
        if (s && typeof s === 'object') {
          this.sourceStatus = s; 
        }
      },
      error: () => {
        // Keep current False state on error
      },
    });
  }

  loadHistory(): void {
    this.syncService.getJobs().subscribe({
      next: (jobs) => { 
        // Ensure we only bind to arrays to avoid NG02200 crash
        if (Array.isArray(jobs)) {
          this.syncJobs = jobs; 
        } else {
          this.syncJobs = [];
        }
      },
      error: (err)  => { 
        this.syncJobs = [];
        console.error('Failed to load job history', err); 
      },
    });
  }

  syncAllWpxf(): void {
    if (this.sourceStatus.api && this.jobs['api'].state === 'idle') this.startSourceSync('api');
    if (this.sourceStatus.wp  && this.jobs['wp'].state  === 'idle') this.startSourceSync('wp');
  }

  startSourceSync(source: 'api' | 'wp'): void {
    const job = this.jobs[source];
    if (job.state !== 'idle') return;

    job.state = 'running';
    job.ingestProgress = 0;
    job.mlProgress = 0;
    job.progressMessage = `Requesting ${source === 'api' ? 'XenForo' : 'WordPress'} sync…`;
    job.errorMessage = '';

    this.syncService.triggerApiSync(source, this.importMode).subscribe({
      next: (res) => {
        job.jobId = res.job_id;
        job.progressMessage = 'Sync scheduled — connecting…';
        this.connectWebSocketForSource(source, res.job_id);
        this.loadHistory();
      },
      error: (err) => {
        job.state = 'failed';
        job.errorMessage = err.error?.error ?? 'Sync request failed.';
      },
    });
  }

  startJsonlImport(): void {
    if (!this.selectedFile) return;
    const job = this.jobs['jsonl'];
    if (job.state !== 'idle') return;

    job.state = 'uploading';
    job.ingestProgress = 0;
    job.mlProgress = 0;
    job.progressMessage = 'Uploading file…';
    job.errorMessage = '';

    this.syncService.uploadFile(this.selectedFile, this.importMode).subscribe({
      next: (res) => {
        job.jobId = res.job_id;
        job.state = 'running';
        job.progressMessage = 'Import scheduled — connecting…';
        this.connectWebSocketForSource('jsonl', res.job_id);
        this.loadHistory();
      },
      error: (err) => {
        job.state = 'failed';
        job.errorMessage = err.error?.error ?? 'Upload failed.';
      },
    });
  }

  resetJob(source: 'api' | 'wp' | 'jsonl'): void {
    const job = this.jobs[source];
    job.ws?.close();
    if (job.pollingInterval) clearInterval(job.pollingInterval);
    this.jobs[source] = this.emptyJob();
    if (source === 'jsonl') { this.selectedFile = null; this.jsonlExpanded = false; }
  }

  private connectWebSocketForSource(source: 'api' | 'wp' | 'jsonl', jobId: string): void {
    const job = this.jobs[source];
    job.ws?.close();

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}/`);
    job.ws = ws;

    ws.onmessage = (event) => {
      let data: any;
      try {
        data = JSON.parse(event.data);
      } catch {
        console.warn('Jobs WebSocket: malformed message', event.data);
        return;
      }

      if (data.type === 'connection.established') {
        job.progressMessage = 'Connected. Waiting for progress…';
        return;
      }

      if (data.type === 'job.progress') {
        job.ingestProgress    = Math.round((data.ingest_progress ?? data.progress ?? 0) * 100);
        job.mlProgress        = Math.round((data.ml_progress ?? 0) * 100);
        job.spacyProgress     = Math.round((data.spacy_progress ?? 0) * 100);
        job.embeddingProgress = Math.round((data.embedding_progress ?? 0) * 100);
        job.progressMessage   = data.message ?? '';

        if (data.state === 'completed') {
          job.state = 'completed';
          job.ingestProgress = 100;
          job.mlProgress = 100;
          job.spacyProgress = 100;
          job.embeddingProgress = 100;
          ws.close();
          this.clearPolling(job);
          this.loadHistory();
        } else if (data.state === 'failed') {
          job.state = 'failed';
          job.errorMessage = data.error ?? 'Import failed.';
          ws.close();
          this.clearPolling(job);
          this.loadHistory();
        } else if (data.state === 'paused') {
          job.state = 'paused';
          ws.close();
          this.clearPolling(job);
          this.loadHistory();
        }
      }
    };

    ws.onerror = () => { if (job.state === 'running') this.startPollingForSource(source, jobId); };
    ws.onclose = () => { if (job.state === 'running') this.startPollingForSource(source, jobId); };
  }

  private startPollingForSource(source: 'api' | 'wp' | 'jsonl', jobId: string): void {
    const job = this.jobs[source];
    if (job.pollingInterval) return;
    job.pollingInterval = setInterval(() => {
      this.syncService.getJob(jobId).subscribe({
        next: (j) => {
          job.ingestProgress    = Math.round((j.ingest_progress ?? j.progress ?? 0) * 100);
          job.mlProgress        = Math.round((j.ml_progress ?? 0) * 100);
          job.spacyProgress     = Math.round((j.spacy_progress ?? 0) * 100);
          job.embeddingProgress = Math.round((j.embedding_progress ?? 0) * 100);
          job.progressMessage   = j.message ?? '';
          if (j.status === 'completed') {
            job.state = 'completed';
            this.clearPolling(job);
            this.loadHistory();
          } else if (j.status === 'failed') {
            job.state = 'failed';
            job.errorMessage = j.error_message ?? 'Import failed.';
            this.clearPolling(job);
            this.loadHistory();
          } else if (j.status === 'paused') {
            job.state = 'paused';
            this.clearPolling(job);
            this.loadHistory();
          }
        },
        error: () => {},
      });
    }, 3000);
  }

  private clearPolling(job: SourceJobState): void {
    if (job.pollingInterval) { clearInterval(job.pollingInterval); job.pollingInterval = null; }
  }

  // ── Drag and drop ───────────────────────────────────────────────

  onDragOver(event: DragEvent): void { event.preventDefault(); this.isDragOver = true; }
  onDragLeave(): void { this.isDragOver = false; }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = false;
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
      this.jobs['jsonl'].errorMessage = 'Only .jsonl files are accepted.';
      return;
    }
    this.jobs['jsonl'].errorMessage = '';
    this.selectedFile = file;
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
    Object.values(this.jobs).forEach(j => {
      j.ws?.close();
      this.clearPolling(j);
    });
    if (this.historyInterval) clearInterval(this.historyInterval);
  }
}
