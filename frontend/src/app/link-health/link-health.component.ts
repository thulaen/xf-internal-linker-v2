import { ChangeDetectionStrategy, Component, DestroyRef, OnDestroy, OnInit, inject, signal } from '@angular/core';
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
import { Subscription, forkJoin, switchMap, timer } from 'rxjs';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { SyncService } from '../jobs/sync.service';
import { DashboardService } from '../dashboard/dashboard.service';
import {
  BrokenLink,
  BrokenLinkService,
  BrokenLinkStatus,
} from './broken-link.service';
import { AuthService } from '../core/services/auth.service';

type LinkHealthFilter = BrokenLinkStatus | 'all';

interface SummaryCounts {
  open: number;
  ignored: number;
  fixed: number;
}

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
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LinkHealthComponent implements OnInit, OnDestroy {
  private brokenLinkSvc = inject(BrokenLinkService);
  private dashboardSvc = inject(DashboardService);
  private syncService = inject(SyncService);
  private snack = inject(MatSnackBar);
  private auth = inject(AuthService);
  private visibilityGate = inject(VisibilityGateService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

  readonly brokenLinks = signal<BrokenLink[]>([]);
  readonly totalCount = signal(0);
  readonly loading = signal(false);

  /** Filter chip — set imperatively via `setStatusFilter`, read via `[selected]`.
   *  No ngModel two-way binding here, so a signal is fine. */
  readonly statusFilter = signal<LinkHealthFilter>('all');
  /** ngModel two-way bound on the HTTP-status mat-select — must be an lvalue. */
  httpStatusFilter: number | null = null;
  readonly page = signal(1);
  readonly pageSize = signal(25);

  /** All three counters live on one signal so a status transition (open → fixed)
   *  is a single atomic update. Previously the mark-status callback did six
   *  sequential `summary.X--` / `summary.X++` mutations on a captured object
   *  reference — under signals that's silent CD breakage; with one atomic
   *  update via `.update()` the bindings always observe a consistent set. */
  readonly summary = signal<SummaryCounts>({ open: 0, ignored: 0, fixed: 0 });

  readonly scanning = signal(false);
  readonly progress = signal(0);
  readonly progressMessage = signal('');
  readonly jobId = signal<string | null>(null);
  readonly errorMessage = signal('');

  readonly displayedColumns: readonly string[] = [
    'source_thread',
    'url',
    'http_status',
    'status',
    'first_detected_at',
    'actions',
  ];

  readonly statusOptions: readonly { value: LinkHealthFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'open', label: 'Open' },
    { value: 'ignored', label: 'Ignored' },
    { value: 'fixed', label: 'Fixed' },
  ];

  readonly httpStatusOptions: readonly { value: number | null; label: string }[] = [
    { value: null, label: 'All status codes' },
    { value: 0, label: 'Connection error (0)' },
    { value: 301, label: '301 redirect' },
    { value: 302, label: '302 redirect' },
    { value: 403, label: '403 forbidden' },
    { value: 404, label: '404 not found' },
    { value: 410, label: '410 gone' },
  ];

  private ws: WebSocket | null = null;
  private pollingSub: Subscription | null = null;

  ngOnInit(): void {
    this.load();
    this.loadSummary();
  }

  ngOnDestroy(): void {
    this.ws?.close();
    this.stopPolling();
  }

  load(): void {
    this.loading.set(true);
    this.brokenLinkSvc.list({
      status: this.statusFilter(),
      http_status: this.httpStatusFilter,
      page: this.page(),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.brokenLinks.set(response.results);
          this.totalCount.set(response.count);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
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
          this.summary.set({
            open: open.count,
            ignored: ignored.count,
            fixed: fixed.count,
          });
          this.dashboardSvc.updateOpenBrokenLinks(open.count);
        },
        error: () => {
          this.snack.open('Failed to load broken-link summary', 'Dismiss', { duration: 4000 });
        },
      });
  }

  setStatusFilter(status: LinkHealthFilter): void {
    this.statusFilter.set(status);
    this.page.set(1);
    this.load();
  }

  onHttpStatusChange(): void {
    this.page.set(1);
    this.load();
  }

  onPageChange(event: PageEvent): void {
    this.page.set(event.pageIndex + 1);
    this.load();
  }

  startScan(): void {
    if (this.scanning()) return;

    this.scanning.set(true);
    this.progress.set(0);
    this.progressMessage.set('Scheduling broken-link scan...');
    this.errorMessage.set('');

    this.brokenLinkSvc.startScan()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ job_id, message }) => {
          this.jobId.set(job_id);
          this.progressMessage.set(message);
          this.connectWebSocket(job_id);
        },
        error: () => {
          this.scanning.set(false);
          this.progressMessage.set('');
          this.snack.open('Failed to start broken-link scan', 'Dismiss', { duration: 4000 });
        },
      });
  }

  exportCsv(): void {
    this.brokenLinkSvc.exportCsv({
      status: this.statusFilter(),
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
            { duration: 2500 },
          );

          // Optimistic local-summary update — avoids the round-trip that
          // `loadSummary` would do. Single atomic update so observers
          // never see a transient state where one bucket has decremented
          // but the other hasn't yet incremented.
          if (oldStatus !== status) {
            this.summary.update((s) => ({
              ...s,
              [oldStatus]: Math.max(0, s[oldStatus] - 1),
              [status]: s[status] + 1,
            }));
            this.dashboardSvc.updateOpenBrokenLinks(this.summary().open);
          }

          this.load();
        },
        error: () => {
          this.snack.open('Failed to update broken link', 'Dismiss', { duration: 4000 });
        },
      });
  }

  openSourceThread(url: string): void {
    if (!url) return;
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
    const base = `${protocol}://${location.host}/ws/jobs/${jobId}/`;
    const token = this.auth.getToken();
    const url = token ? `${base}?token=${encodeURIComponent(token)}` : base;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      // If a previous connect attempt switched to HTTP polling on
      // `onerror` / `onclose`, kill that interval now that the socket
      // is healthy — otherwise we'd poll AND receive WS frames for the
      // same job during recovery.
      this.stopPolling();
      this.errorMessage.set('');
    };

    this.ws.onmessage = (event) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // Ignore malformed WebSocket messages
      }

      if (data['type'] === 'connection.established') {
        this.progressMessage.set('Connected. Waiting for scan progress...');
        return;
      }

      if (data['type'] !== 'job.progress') {
        return;
      }

      this.progress.set(Math.round(((data['progress'] as number) ?? 0) * 100));
      this.progressMessage.set((data['message'] as string) ?? '');

      if (data['state'] === 'completed') {
        this.scanning.set(false);
        this.progress.set(100);
        this.ws?.close();
        this.stopPolling();
        this.load();
        this.loadSummary();
        this.snack.open('Broken-link scan complete', undefined, { duration: 3000 });
      } else if (data['state'] === 'failed') {
        this.scanning.set(false);
        const err = (data['error'] as string) ?? 'Broken-link scan failed.';
        this.errorMessage.set(err);
        this.ws?.close();
        this.stopPolling();
        this.snack.open(err, 'Dismiss', { duration: 5000 });
      }
    };

    this.ws.onerror = () => {
      if (this.scanning()) {
        this.errorMessage.set('WebSocket error — switching to polling...');
        this.startPolling(jobId);
      }
    };

    this.ws.onclose = () => {
      if (this.scanning()) {
        this.errorMessage.set('Connection closed — switching to polling...');
        this.startPolling(jobId);
      }
    };
  }

  private startPolling(jobId: string): void {
    if (this.pollingSub) return;
    // Polling pauses while the tab is hidden or the user signs out.
    // See docs/PERFORMANCE.md §13.
    //
    // switchMap flattens the timer-of-fetches into a single stream so
    // each tick auto-cancels the previous in-flight getJob and inherits
    // the outer takeUntilDestroyed. The previous nested subscribe could
    // leave a dangling inner request if the timer ticked again before
    // the previous response landed.
    this.pollingSub = this.visibilityGate
      .whileLoggedInAndVisible(() => timer(3000, 3000))
      .pipe(
        switchMap(() => this.syncService.getJob(jobId)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (job) => {
          this.progress.set(Math.round((job.progress ?? 0) * 100));
          this.progressMessage.set(job.message ?? '');

          if (job.status === 'completed') {
            this.scanning.set(false);
            this.progress.set(100);
            this.stopPolling();
            this.load();
            this.loadSummary();
            this.snack.open('Broken-link scan complete', undefined, { duration: 3000 });
          } else if (job.status === 'failed') {
            this.scanning.set(false);
            const err = job.error_message ?? 'Broken-link scan failed.';
            this.errorMessage.set(err);
            this.stopPolling();
            this.snack.open(err, 'Dismiss', { duration: 5000 });
          }
        },
        error: () => {
          // Silent retry — switchMap's next tick will re-subscribe.
        },
      });
  }

  private stopPolling(): void {
    this.pollingSub?.unsubscribe();
    this.pollingSub = null;
  }
}
