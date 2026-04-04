import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDividerModule } from '@angular/material/divider';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { SyncService, SyncJob } from './sync.service';

type ImportState = 'idle' | 'uploading' | 'running' | 'completed' | 'failed';

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
  // ── File selection ──────────────────────────────────────────────
  selectedFile: File | null = null;
  importMode = 'full';
  isDragOver = false;

  // ── Active Job state ────────────────────────────────────────────
  state: ImportState = 'idle';
  progress = 0;
  ingestProgress = 0;
  mlProgress = 0;
  progressMessage = '';
  jobId: string | null = null;
  errorMessage = '';

  // ── Connection status ────────────────────────────────────────────
  sourceStatus: { api: boolean; wp: boolean } = { api: false, wp: false };

  // ── History ─────────────────────────────────────────────────────
  syncJobs: SyncJob[] = [];
  displayedColumns: string[] = ['created_at', 'source', 'mode', 'status', 'progress', 'actions'];
  source: 'api' | 'wp' | 'jsonl' = 'jsonl';

  setSource(s: 'api' | 'wp' | 'jsonl'): void {
    if (this.isRunning) return;
    this.source = s;
    this.reset();
  }

  private syncService = inject(SyncService);
  private ws: WebSocket | null = null;
  private pollingInterval: any;

  readonly modes = [
    { value: 'full',   label: 'Full import',   hint: 'Body text, sentences, embeddings' },
    { value: 'titles', label: 'Titles only',   hint: 'Metadata + PageRank / velocity'  },
    { value: 'quick',  label: 'Quick check',   hint: 'IDs and titles only'             },
  ];

  ngOnInit(): void {
    this.loadHistory();
    this.loadSourceStatus();
  }

  loadSourceStatus(): void {
    this.syncService.getSourceStatus().subscribe({
      next: (status) => { this.sourceStatus = status; },
      error: () => {},
    });
  }

  loadHistory(): void {
    this.syncService.getJobs().subscribe({
      next: (jobs: SyncJob[]) => {
        this.syncJobs = jobs;
      },
      error: (err: any) => {
        console.error('Failed to load job history', err);
      }
    });
  }

  get fileSizeLabel(): string {
    if (!this.selectedFile) return '';
    const mb = this.selectedFile.size / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(this.selectedFile.size / 1024).toFixed(0)} KB`;
  }

  get isRunning(): boolean {
    return this.state === 'uploading' || this.state === 'running';
  }

  // ── Drag-and-drop ───────────────────────────────────────────────

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = true;
  }

  onDragLeave(): void {
    this.isDragOver = false;
  }

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
      this.errorMessage = 'Only .jsonl files are accepted.';
      return;
    }
    this.errorMessage = '';
    this.selectedFile = file;
    this.state = 'idle';
    this.progress = 0;
    this.progressMessage = '';
  }

  // ── Import Actions ──────────────────────────────────────────────

  startImport(): void {
    if (!this.selectedFile || this.isRunning) return;

    this.state = 'uploading';
    this.progress = 0;
    this.ingestProgress = 0;
    this.mlProgress = 0;
    this.progressMessage = 'Uploading file…';
    this.errorMessage = '';

    this.syncService.uploadFile(this.selectedFile, this.importMode).subscribe({
      next: (res: { job_id: string; file: string; mode: string }) => {
        this.jobId = res.job_id;
        this.state = 'running';
        this.progressMessage = 'Import scheduled — connecting…';
        this.connectWebSocket(res.job_id);
        this.loadHistory(); // Refresh history to show the new pending job
      },
      error: (err: any) => {
        this.state = 'failed';
        this.errorMessage = err.error?.error ?? 'Upload failed. Please try again.';
      },
    });
  }

  startApiSync(source: 'api' | 'wp'): void {
    if (this.isRunning) return;

    this.state = 'running';
    this.progress = 0;
    this.ingestProgress = 0;
    this.mlProgress = 0;
    this.progressMessage = `Requesting ${source === 'api' ? 'XenForo' : 'WordPress'} sync…`;
    this.errorMessage = '';

    this.syncService.triggerApiSync(source, this.importMode).subscribe({
      next: (res: { job_id: string; source: string; mode: string }) => {
        this.jobId = res.job_id;
        this.progressMessage = 'Sync scheduled — connecting…';
        this.connectWebSocket(res.job_id);
        this.loadHistory();
      },
      error: (err: any) => {
        this.state = 'failed';
        this.errorMessage = err.error?.error ?? 'Sync request failed. Please try again.';
      },
    });
  }

  private connectWebSocket(jobId: string): void {
    this.ws?.close();

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}/`);

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'connection.established') {
        this.progressMessage = 'Connected. Waiting for progress...';
        return;
      }

      if (data.type === 'job.progress') {
        this.progress = Math.round((data.progress ?? 0) * 100);
        this.ingestProgress = Math.round((data.ingest_progress ?? (data.progress || 0)) * 100);
        this.mlProgress = Math.round((data.ml_progress ?? 0) * 100);
        this.progressMessage = data.message ?? '';

        if (data.state === 'completed') {
          this.state = 'completed';
          this.progress = 100;
          this.ingestProgress = 100;
          this.mlProgress = 100;
          this.ws?.close();
          this.stopPolling();
          this.loadHistory(); // Refresh history on completion
        } else if (data.state === 'failed') {
          this.state = 'failed';
          this.errorMessage = data.error ?? 'Import failed.';
          this.ws?.close();
          this.stopPolling();
          this.loadHistory(); // Refresh history on failure
        }
      }
    };

    this.ws.onerror = () => {
      if (this.state === 'running') {
        this.progressMessage = 'WebSocket error — switching to polling...';
        this.startPolling(jobId);
      }
    };

    this.ws.onclose = () => {
      if (this.state === 'running') {
        this.progressMessage = 'Connection closed — switching to polling...';
        this.startPolling(jobId);
      }
    };
  }

  private startPolling(jobId: string): void {
    if (this.pollingInterval) return;
    this.pollingInterval = setInterval(() => {
      this.syncService.getJob(jobId).subscribe({
        next: (job) => {
          this.progress = Math.round((job.progress ?? 0) * 100);
          this.progressMessage = job.message ?? '';

          if (job.status === 'completed') {
            this.state = 'completed';
            this.progress = 100;
            this.stopPolling();
            this.loadHistory();
          } else if (job.status === 'failed') {
            this.state = 'failed';
            this.errorMessage = job.error_message ?? 'Import failed.';
            this.stopPolling();
            this.loadHistory();
          }
        },
        error: () => {
          // Silent fail for polling, will retry next interval
        }
      });
    }, 3000);
  }

  private stopPolling(): void {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
  }

  // ── UI Helpers ──────────────────────────────────────────────────

  getStatusIcon(status: string): string {
    switch (status) {
      case 'completed': return 'check_circle';
      case 'failed': return 'error';
      case 'running': return 'sync';
      case 'pending': return 'schedule';
      default: return 'help_outline';
    }
  }

  getStatusClass(status: string): string {
    return `status-${status}`;
  }

  reset(): void {
    this.ws?.close();
    this.ws = null;
    this.stopPolling();
    this.selectedFile = null;
    this.state = 'idle';
    this.progress = 0;
    this.progressMessage = '';
    this.jobId = null;
    this.errorMessage = '';
  }

  ngOnDestroy(): void {
    this.ws?.close();
    this.stopPolling();
  }
}
