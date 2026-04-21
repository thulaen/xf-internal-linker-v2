import { Component, DestroyRef, OnDestroy, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin } from 'rxjs';
import { SyncService } from '../jobs/sync.service';
import { DashboardService } from '../dashboard/dashboard.service';
import {
  BrokenLink,
  BrokenLinkService,
  BrokenLinkStatus,
} from './broken-link.service';

type LinkHealthFilter = BrokenLinkStatus | 'all';

@Component({
  selector: 'app-link-health',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatPaginatorModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
  ],
  templateUrl: './link-health.component.html',
  styleUrls: ['./link-health.component.scss'],
})
export class LinkHealthComponent implements OnInit, OnDestroy {
  private brokenLinkSvc = inject(BrokenLinkService);
  private dashboardSvc = inject(DashboardService);
  private syncService = inject(SyncService);
  private snack = inject(MatSnackBar);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

  brokenLinks: BrokenLink[] = [];
  totalCount = 0;
  loading = false;

  statusFilter: LinkHealthFilter = 'all';
  httpStatusFilter: number | null = null;
  page = 1;
  pageSize = 25;

  summary = {
    open: 0,
    ignored: 0,
    fixed: 0,
  };

  scanning = false;
  progress = 0;
  progressMessage = '';
  jobId: string | null = null;
  errorMessage = '';

  displayedColumns = [
    'source_thread',
    'url',
    'http_status',
    'status',
    'first_detected_at',
    'actions',
  ];

  statusOptions: Array<{ value: LinkHealthFilter; label: string }> = [
    { value: 'all', label: 'All' },
    { value: 'open', label: 'Open' },
    { value: 'ignored', label: 'Ignored' },
    { value: 'fixed', label: 'Fixed' },
  ];

  httpStatusOptions: Array<{ value: number | null; label: string }> = [
    { value: null, label: 'All status codes' },
    { value: 0, label: 'Connection error (0)' },
    { value: 301, label: '301 redirect' },
    { value: 302, label: '302 redirect' },
    { value: 403, label: '403 forbidden' },
    { value: 404, label: '404 not found' },
    { value: 410, label: '410 gone' },
  ];

  private ws: WebSocket | null = null;
  private pollingInterval: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.load();
    this.loadSummary();
  }

  ngOnDestroy(): void {
    this.ws?.close();
    this.stopPolling();
  }

  load(): void {
    this.loading = true;
    this.brokenLinkSvc.list({
      status: this.statusFilter,
      http_status: this.httpStatusFilter,
      page: this.page,
    })
    .pipe(takeUntilDestroyed(this.destroyRef))
    .subscribe({
      next: (response) => {
        this.brokenLinks = response.results;
        this.totalCount = response.count;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load broken links', 'Dismiss', { duration: 4000 });
      },
    });
  }

  loadSummary(): void {
    forkJoin({
      open: this.brokenLinkSvc.list({ status: 'open' }),
      ignored: this.brokenLinkSvc.list({ status: 'ignored' }),
      fixed: this.brokenLinkSvc.list({ status: 'fixed' }),
    })
    .pipe(takeUntilDestroyed(this.destroyRef))
    .subscribe({
      next: ({ open, ignored, fixed }) => {
        this.summary = {
          open: open.count,
          ignored: ignored.count,
          fixed: fixed.count,
        };
        this.dashboardSvc.updateOpenBrokenLinks(open.count);
      },
      error: () => {
        this.snack.open('Failed to load broken-link summary', 'Dismiss', { duration: 4000 });
      },
    });
  }

  setStatusFilter(status: LinkHealthFilter): void {
    this.statusFilter = status;
    this.page = 1;
    this.load();
  }

  onHttpStatusChange(): void {
    this.page = 1;
    this.load();
  }

  onPageChange(event: PageEvent): void {
    this.page = event.pageIndex + 1;
    this.load();
  }

  startScan(): void {
    if (this.scanning) {
      return;
    }

    this.scanning = true;
    this.progress = 0;
    this.progressMessage = 'Scheduling broken-link scan...';
    this.errorMessage = '';

    this.brokenLinkSvc.startScan()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: ({ job_id, message }) => {
        this.jobId = job_id;
        this.progressMessage = message;
        this.connectWebSocket(job_id);
      },
      error: () => {
        this.scanning = false;
        this.progressMessage = '';
        this.snack.open('Failed to start broken-link scan', 'Dismiss', { duration: 4000 });
      },
    });
  }

  exportCsv(): void {
    this.brokenLinkSvc.exportCsv({
      status: this.statusFilter,
      http_status: this.httpStatusFilter,
    })
    .pipe(takeUntilDestroyed(this.destroyRef))
    .subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `broken-links-${new Date().toISOString().slice(0, 10)}.csv`;
        anchor.click();
        window.URL.revokeObjectURL(url);
      },
      error: () => {
        this.snack.open('Failed to export CSV', 'Dismiss', { duration: 4000 });
      },
    });
  }

  markStatus(link: BrokenLink, status: BrokenLinkStatus): void {
    const oldStatus = link.status;
    this.brokenLinkSvc.patch(link.broken_link_id, { status })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.snack.open(
          status === 'fixed' ? 'Marked as fixed' : 'Broken link ignored',
          undefined,
          { duration: 2500 }
        );

        // Update local summary counts to avoid redundant summary fetch
        if (oldStatus !== status) {
          if (oldStatus === 'open') this.summary.open--;
          if (oldStatus === 'ignored') this.summary.ignored--;
          if (oldStatus === 'fixed') this.summary.fixed--;

          if (status === 'open') this.summary.open++;
          if (status === 'ignored') this.summary.ignored++;
          if (status === 'fixed') this.summary.fixed++;

          this.dashboardSvc.updateOpenBrokenLinks(this.summary.open);
        }

        this.load();
      },
      error: () => {
        this.snack.open('Failed to update broken link', 'Dismiss', { duration: 4000 });
      },
    });
  }

  openSourceThread(url: string): void {
    if (!url) {
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  trackById(_: number, link: BrokenLink): string {
    return link.broken_link_id;
  }

  statusLabel(httpStatus: number): string {
    return httpStatus === 0 ? 'Connection error' : String(httpStatus);
  }

  private connectWebSocket(jobId: string): void {
    this.ws?.close();

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${protocol}://${location.host}/ws/jobs/${jobId}/`);

    this.ws.onopen = () => {
      // If a previous connect attempt switched to HTTP polling on
      // `onerror` / `onclose`, kill that interval now that the socket
      // is healthy — otherwise we'd poll AND receive WS frames for the
      // same job during recovery.
      this.stopPolling();
      this.errorMessage = '';
    };

    this.ws.onmessage = (event) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // Ignore malformed WebSocket messages
      }

      if (data['type'] === 'connection.established') {
        this.progressMessage = 'Connected. Waiting for scan progress...';
        return;
      }

      if (data['type'] !== 'job.progress') {
        return;
      }

      this.progress = Math.round(((data['progress'] as number) ?? 0) * 100);
      this.progressMessage = (data['message'] as string) ?? '';

      if (data['state'] === 'completed') {
        this.scanning = false;
        this.progress = 100;
        this.ws?.close();
        this.stopPolling();
        this.load();
        this.loadSummary();
        this.snack.open('Broken-link scan complete', undefined, { duration: 3000 });
      } else if (data['state'] === 'failed') {
        this.scanning = false;
        this.errorMessage = (data['error'] as string) ?? 'Broken-link scan failed.';
        this.ws?.close();
        this.stopPolling();
        this.snack.open(this.errorMessage, 'Dismiss', { duration: 5000 });
      }
    };

    this.ws.onerror = () => {
      if (this.scanning) {
        this.errorMessage = 'WebSocket error — switching to polling...';
        this.startPolling(jobId);
      }
    };

    this.ws.onclose = () => {
      if (this.scanning) {
        this.errorMessage = 'Connection closed — switching to polling...';
        this.startPolling(jobId);
      }
    };
  }

  private startPolling(jobId: string): void {
    if (this.pollingInterval) return;
    this.pollingInterval = setInterval(() => {
      this.syncService.getJob(jobId)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
        next: (job) => {
          this.progress = Math.round((job.progress ?? 0) * 100);
          this.progressMessage = job.message ?? '';

          if (job.status === 'completed') {
            this.scanning = false;
            this.progress = 100;
            this.stopPolling();
            this.load();
            this.loadSummary();
            this.snack.open('Broken-link scan complete', undefined, { duration: 3000 });
          } else if (job.status === 'failed') {
            this.scanning = false;
            this.errorMessage = job.error_message ?? 'Broken-link scan failed.';
            this.stopPolling();
            this.snack.open(this.errorMessage, 'Dismiss', { duration: 5000 });
          }
        },
        error: () => {
          // Silent retry
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
}
