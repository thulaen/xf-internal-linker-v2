/**
 * NotificationCenterComponent
 *
 * The bell icon button that lives in the toolbar and the slide-over panel
 * that shows recent alerts.  The parent (AppComponent) owns the open/close
 * state so the panel can be dismissed from outside.
 */

import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  EventEmitter,
  Input,
  OnInit,
  Output,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NotificationCenterComponent implements OnInit {
  /** Whether the panel is open. Two-way bound from AppComponent. */
  @Input() open = false;
  @Output() openChange = new EventEmitter<boolean>();
  @Output() closed = new EventEmitter<void>();

  protected notifSvc = inject(NotificationService);
  private router = inject(Router);
  private destroyRef = inject(DestroyRef);

  // Internal state lives in signals so OnPush change detection picks up
  // every mutation automatically — no `cdr.markForCheck()` sprinkled
  // through subscribe callbacks. Use `.set()` for whole-value writes
  // and `.update()` for in-place transforms (filter, push, etc).
  readonly alerts = signal<OperatorAlert[]>([]);
  readonly loading = signal(false);

  ngOnInit(): void {
    this.loadAlerts();
    // Refresh when a new alert arrives via WebSocket
    this.notifSvc.newAlert$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadAlerts());
  }

  loadAlerts(): void {
    this.loading.set(true);
    // The list endpoint is paginated; the dropdown only ever shows the
    // first page (default 25) of unread alerts — the full list lives at
    // /alerts behind a mat-paginator. Ignore the count/next/previous
    // envelope here; we just want the items.
    this.notifSvc
      .loadAlerts({ status: 'unread' })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (paged) => {
          this.alerts.set(paged.results);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
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
    this.notifSvc.acknowledgeAll()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => { this.alerts.set([]); },
      error: () => { this.loadAlerts(); },
    });
  }

  onAcknowledge(alert: OperatorAlert, event: Event): void {
    event.stopPropagation();
    this.notifSvc.acknowledge(alert.alert_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => { this.alerts.update((arr) => arr.filter((a) => a.alert_id !== alert.alert_id)); },
      error: () => { this.loadAlerts(); },
    });
  }

  onOpenRelated(alert: OperatorAlert): void {
    this.notifSvc.markRead(alert.alert_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      error: () => { /* error interceptor handles display */ },
    });
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
