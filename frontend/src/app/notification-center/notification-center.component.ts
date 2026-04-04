/**
 * NotificationCenterComponent
 *
 * The bell icon button that lives in the toolbar and the slide-over panel
 * that shows recent alerts.  The parent (AppComponent) owns the open/close
 * state so the panel can be dismissed from outside.
 */

import {
  Component,
  EventEmitter,
  Input,
  OnInit,
  Output,
  inject,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { Router } from '@angular/router';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  NotificationService,
  OperatorAlert,
} from '../core/services/notification.service';

@Component({
  selector: 'app-notification-center',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    MatBadgeModule,
    MatButtonModule,
    MatDividerModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './notification-center.component.html',
  styleUrls: ['./notification-center.component.scss'],
})
export class NotificationCenterComponent implements OnInit {
  /** Whether the panel is open. Two-way bound from AppComponent. */
  @Input() open = false;
  @Output() openChange = new EventEmitter<boolean>();
  @Output() closed = new EventEmitter<void>();

  protected notifSvc = inject(NotificationService);
  private router = inject(Router);

  alerts: OperatorAlert[] = [];
  loading = false;

  ngOnInit(): void {
    this.loadAlerts();
    // Refresh when a new alert arrives via WebSocket
    this.notifSvc.newAlert$.subscribe(() => this.loadAlerts());
  }

  loadAlerts(): void {
    this.loading = true;
    this.notifSvc
      .loadAlerts({ status: 'unread' })
      .subscribe({
        next: (data) => {
          this.alerts = data;
          this.loading = false;
        },
        error: () => {
          this.loading = false;
        },
      });
  }

  close(): void {
    this.open = false;
    this.openChange.emit(false);
    this.closed.emit();
  }

  openPanel(): void {
    this.open = true;
    this.openChange.emit(true);
  }

  onAcknowledgeAll(): void {
    this.notifSvc.acknowledgeAll().subscribe(() => {
      this.alerts = [];
    });
  }

  onAcknowledge(alert: OperatorAlert, event: Event): void {
    event.stopPropagation();
    this.notifSvc.acknowledge(alert.alert_id).subscribe(() => {
      this.alerts = this.alerts.filter((a) => a.alert_id !== alert.alert_id);
    });
  }

  onOpenRelated(alert: OperatorAlert): void {
    this.notifSvc.markRead(alert.alert_id).subscribe();
    if (alert.related_route) {
      this.router.navigateByUrl(alert.related_route);
    }
    this.close();
  }

  openAlertsPage(): void {
    this.router.navigateByUrl('/alerts');
    this.close();
  }

  severityIcon(severity: string): string {
    const map: Record<string, string> = {
      info: 'info',
      success: 'check_circle',
      warning: 'warning',
      error: 'error',
      urgent: 'priority_high',
    };
    return map[severity] ?? 'notifications';
  }
}
