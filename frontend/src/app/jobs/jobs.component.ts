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
import { SyncService, SyncJob } from './sync.service';

type ImportState = 'idle' | 'uploading' | 'running' | 'completed' | 'failed';

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

  readonly modes = [
    { value: 'full',   label: 'Full import',  hint: 'Body text, sentences, embeddings' },
    { value: 'titles', label: 'Titles only',  hint: 'Metadata + PageRank / velocity'  },
    { value: 'quick',  label: 'Quick check',  hint: 'IDs and titles only'             },
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
    if (job.status === 'failed' && job.error_message) return job.error_message;
    return job.status;
  }

  ngOnInit(): void {
    this.loadHistory();
    this.loadSourceStatus();
    // Refresh the history table every 30 seconds so status changes are visible.
    this.historyInterval = setInterval(() => this.loadHistory(), 30_000);
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
