import { Component, OnInit, inject, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { SyncService, WebhookReceipt } from '../../../jobs/sync.service';

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
  
  receipts: WebhookReceipt[] = [];
  displayedColumns: string[] = ['created_at', 'source', 'event_type', 'status'];
  
  private refreshInterval: any;

  ngOnInit(): void {
    this.load();
    // Refresh every 10 seconds for real-time feel
    this.refreshInterval = setInterval(() => this.load(), 10000);
  }

  ngOnDestroy(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  load(): void {
    this.syncSvc.getWebhookReceipts().subscribe({
      next: (data) => {
        this.receipts = data.slice(0, 10); // Show last 10
      },
      error: (err) => console.error('Failed to load webhook logs', err)
    });
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
