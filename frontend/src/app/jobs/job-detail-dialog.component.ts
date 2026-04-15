import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { SyncJob } from './sync.service';

export interface JobDetailDialogData {
  job: SyncJob;
}

export interface JobDetailDialogResult {
  action: 'retry' | 'resume';
  source?: 'api' | 'wp';
  mode?: string;
  jobId?: string;
}

@Component({
  selector: 'app-job-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">{{ job.status === 'failed' ? 'error' : 'info' }}</mat-icon>
      Job Details
    </h2>

    <mat-dialog-content>
      <div class="detail-grid">
        <div class="detail-row">
          <span class="detail-label">Source</span>
          <span class="detail-value">{{ sourceLabel }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Mode</span>
          <span class="detail-value">{{ modeLabel }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Status</span>
          <span class="detail-value status-value" [class]="'status-' + job.status">{{ job.status }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Items synced</span>
          <span class="detail-value">{{ job.items_synced | number }}</span>
        </div>
        <div class="detail-row" *ngIf="job.started_at">
          <span class="detail-label">Started</span>
          <span class="detail-value">{{ job.started_at | date:'MMM d, y HH:mm:ss' }}</span>
        </div>
        <div class="detail-row" *ngIf="job.completed_at">
          <span class="detail-label">Finished</span>
          <span class="detail-value">{{ job.completed_at | date:'MMM d, y HH:mm:ss' }}</span>
        </div>
        <div class="detail-row" *ngIf="job.is_resumable && job.checkpoint_stage">
          <span class="detail-label">Checkpoint</span>
          <span class="detail-value">{{ job.checkpoint_stage }} after {{ job.checkpoint_items_processed | number }} items</span>
        </div>
      </div>

      <div class="message-section" *ngIf="job.message">
        <span class="section-label">Last message</span>
        <p class="message-text">{{ job.message }}</p>
      </div>

      <div class="error-section" *ngIf="job.error_message">
        <span class="section-label">Error</span>
        <p class="error-text">{{ job.error_message }}</p>
      </div>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Close</button>
      <button mat-flat-button color="primary"
        *ngIf="canResume"
        (click)="resume()">
        <mat-icon>play_arrow</mat-icon>
        Resume
      </button>
      <button mat-flat-button color="primary"
        *ngIf="job.status === 'failed' && canRetry"
        (click)="retry()">
        <mat-icon>replay</mat-icon>
        Retry
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; }

    h2[mat-dialog-title] {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 18px;
      font-weight: 500;
    }

    .title-icon {
      color: var(--color-text-secondary);
    }

    .detail-grid {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 8px 16px;
      margin-bottom: 16px;
    }

    .detail-label {
      font-size: 12px;
      color: var(--color-text-muted);
      font-weight: 500;
    }

    .detail-value {
      font-size: 13px;
      color: var(--color-text-primary);
    }

    .status-value {
      font-weight: 500;
      text-transform: capitalize;
    }

    .status-failed { color: var(--color-error); }
    .status-completed { color: var(--color-success); }
    .status-running { color: var(--color-primary); }

    .section-label {
      font-size: 12px;
      font-weight: 500;
      color: var(--color-text-muted);
      display: block;
      margin-bottom: 4px;
    }

    .message-text {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 12px;
    }

    .error-section {
      background: var(--color-error-bg, #fce8e6);
      border-radius: var(--card-border-radius);
      padding: 12px;
    }

    .error-text {
      font-size: 13px;
      color: var(--color-error);
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
    }

    mat-dialog-actions button mat-icon {
      margin-right: 4px;
    }
  `],
})
export class JobDetailDialogComponent {
  private dialogRef = inject(MatDialogRef<JobDetailDialogComponent>);
  private data: JobDetailDialogData = inject(MAT_DIALOG_DATA);

  get job(): SyncJob {
    return this.data.job;
  }

  get sourceLabel(): string {
    if (this.job.source === 'api') return 'XenForo';
    if (this.job.source === 'wp') return 'WordPress';
    return 'JSONL File';
  }

  get modeLabel(): string {
    if (this.job.mode === 'full') return 'Full import';
    if (this.job.mode === 'titles') return 'Titles only';
    if (this.job.mode === 'quick') return 'Quick check';
    return this.job.mode;
  }

  get canRetry(): boolean {
    return this.job.source === 'api' || this.job.source === 'wp';
  }

  get canResume(): boolean {
    return this.job.is_resumable
      && !!this.job.checkpoint_stage
      && ['paused', 'failed', 'cancelled'].includes(this.job.status);
  }

  retry(): void {
    const result: JobDetailDialogResult = {
      action: 'retry',
      source: this.job.source as 'api' | 'wp',
      mode: this.job.mode,
    };
    this.dialogRef.close(result);
  }

  resume(): void {
    this.dialogRef.close({
      action: 'resume',
      jobId: this.job.job_id,
    });
  }
}
