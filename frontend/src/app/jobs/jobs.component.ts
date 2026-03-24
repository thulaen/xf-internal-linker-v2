import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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
  progressMessage = '';
  jobId: string | null = null;
  errorMessage = '';

  // ── History ─────────────────────────────────────────────────────
  syncJobs: SyncJob[] = [];
  displayedColumns: string[] = ['created_at', 'source', 'mode', 'status', 'progress', 'actions'];

  private ws: WebSocket | null = null;

  readonly modes = [
    { value: 'full',   label: 'Full import',   hint: 'Body text, sentences, embeddings' },
    { value: 'titles', label: 'Titles only',   hint: 'Metadata + PageRank / velocity'  },
    { value: 'quick',  label: 'Quick check',   hint: 'IDs and titles only'             },
  ];

  constructor(private syncService: SyncService) {}

  ngOnInit(): void {
    this.loadHistory();
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
        this.progressMessage = data.message ?? '';

        if (data.state === 'completed') {
          this.state = 'completed';
          this.progress = 100;
          this.ws?.close();
          this.loadHistory(); // Refresh history on completion
        } else if (data.state === 'failed') {
          this.state = 'failed';
          this.errorMessage = data.error ?? 'Import failed.';
          this.ws?.close();
          this.loadHistory(); // Refresh history on failure
        }
      }
    };

    this.ws.onerror = () => {
      this.progressMessage = 'WebSocket error — progress updates unavailable.';
    };
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
    this.selectedFile = null;
    this.state = 'idle';
    this.progress = 0;
    this.progressMessage = '';
    this.jobId = null;
    this.errorMessage = '';
  }

  ngOnDestroy(): void {
    this.ws?.close();
  }
}
