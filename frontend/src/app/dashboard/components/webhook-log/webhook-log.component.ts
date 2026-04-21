import { Component, OnInit, inject, OnDestroy, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SyncService, WebhookReceipt } from '../../../jobs/sync.service';
import { RealtimeService } from '../../../core/services/realtime.service';
import { TopicUpdate } from '../../../core/services/realtime.types';

/**
 * Webhook Log — last 10 webhook receipts.
 *
 * Phase R1.5: live updates via the `webhooks.receipts` realtime topic.
 * The previous 10-second interval polling is replaced by instant push;
 * a 60-second defensive fallback remains in case the WebSocket is briefly
 * disconnected.
 */
@Component({
  selector: 'app-webhook-log',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule,
    MatIconModule,
    MatTooltipModule,
  ],
  templateUrl: './webhook-log.component.html',
  styleUrls: ['./webhook-log.component.scss']
})
export class WebhookLogComponent implements OnInit, OnDestroy {
  private syncSvc = inject(SyncService);
  private realtime = inject(RealtimeService);
  private destroyRef = inject(DestroyRef);

  receipts: WebhookReceipt[] = [];
  /* Audit M4 (2026-04-20): added `detail` column so the table fills
     the full card width instead of leaving the right ~35% blank.
     The detail column shows the error message when present, otherwise
     a human-readable "last seen" or a quiet dash. */
  displayedColumns: string[] = ['created_at', 'source', 'event_type', 'detail', 'status'];

  private readonly MAX_ROWS = 10;
  private refreshInterval: any;

  ngOnInit(): void {
    this.load();

    this.realtime
      .subscribeTopic('webhooks.receipts')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((update: TopicUpdate) => this.handleRealtimeUpdate(update));

    // Defensive safety net: if the WebSocket drops for longer than the
    // reconnect backoff, refresh the list every minute so the table can
    // never go stale for more than 60s. Skip when the tab is hidden
    // (no operator looking; realtime reconnect will catch up). See
    // docs/PERFORMANCE.md §13.
    this.refreshInterval = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      this.load();
    }, 60_000);
  }

  ngOnDestroy(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  load(): void {
    this.syncSvc.getWebhookReceipts()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (data) => {
        this.receipts = data.slice(0, this.MAX_ROWS);
      },
      error: (err) => console.error('Failed to load webhook logs', err)
    });
  }

  private handleRealtimeUpdate(update: TopicUpdate): void {
    if (update.event === 'receipt.deleted') {
      const id = (update.payload as { receipt_id: string }).receipt_id;
      this.receipts = this.receipts.filter((r) => r.receipt_id !== id);
      return;
    }
    if (update.event === 'receipt.created' || update.event === 'receipt.updated') {
      const next = update.payload as WebhookReceipt;
      const idx = this.receipts.findIndex((r) => r.receipt_id === next.receipt_id);
      if (idx >= 0) {
        this.receipts = this.receipts.map((r) => (r.receipt_id === next.receipt_id ? next : r));
      } else {
        // New receipt → prepend, cap list at MAX_ROWS so the table stays tidy.
        this.receipts = [next, ...this.receipts].slice(0, this.MAX_ROWS);
      }
    }
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case 'processed': return 'check_circle';
      case 'ignored':   return 'visibility_off';
      case 'error':     return 'error';
      default:          return 'help_outline';
    }
  }

  getStatusClass(status: string): string {
    return `status-${status}`;
  }
}
