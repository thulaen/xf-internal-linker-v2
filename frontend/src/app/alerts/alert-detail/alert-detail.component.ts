import { Component, OnInit, inject, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { NotificationService, OperatorAlert } from '../../core/services/notification.service';

type AlertDetail = OperatorAlert;

@Component({
  selector: 'app-alert-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, MatButtonModule, MatCardModule, MatChipsModule, MatIconModule, MatProgressSpinnerModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading) {
      <div class="center-spinner"><mat-spinner diameter="36" /></div>
    } @else if (loadError) {
      <mat-card class="detail-card" data-ga4-panel>
        <mat-card-content>
          <p class="alert-message">{{ loadError }}</p>
        </mat-card-content>
        <mat-card-actions align="end">
          <a mat-button routerLink="/alerts">Back to alerts</a>
        </mat-card-actions>
      </mat-card>
    } @else if (alert) {
      <mat-card class="detail-card" data-ga4-panel>
        <mat-card-header>
          <mat-icon mat-card-avatar [class]="'severity-' + alert.severity">
            {{ severityIcon(alert.severity) }}
          </mat-icon>
          <mat-card-title>{{ alert.title }}</mat-card-title>
          <mat-card-subtitle>{{ alert.event_type }} · {{ alert.source_area }}</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="alert-message">{{ alert.message }}</p>
          <div class="meta-grid">
            <div class="meta-item"><span class="meta-label">Status</span><mat-chip disableRipple>{{ alert.status }}</mat-chip></div>
            <div class="meta-item"><span class="meta-label">Severity</span><mat-chip [class]="'severity-chip-' + alert.severity" disableRipple>{{ alert.severity }}</mat-chip></div>
            <div class="meta-item"><span class="meta-label">Occurrences</span><span>{{ alert.occurrence_count }}x</span></div>
            <div class="meta-item"><span class="meta-label">First seen</span><span>{{ alert.first_seen_at | date:'medium' }}</span></div>
            <div class="meta-item"><span class="meta-label">Last seen</span><span>{{ alert.last_seen_at | date:'medium' }}</span></div>
            @if (alert.suppressed_until) {
              <div class="meta-item"><span class="meta-label">Muted until</span><span>{{ alert.suppressed_until | date:'medium' }}</span></div>
            }
          </div>
        </mat-card-content>
        <mat-card-actions align="end">
          @if (alert.related_route) {
            <a mat-button [routerLink]="alert.related_route">Go to source</a>
          }
          <a mat-button routerLink="/alerts">Back to alerts</a>
        </mat-card-actions>
      </mat-card>
    }
  `,
  styles: [`
    .center-spinner { display: flex; justify-content: center; padding: 48px; }
    .detail-card { border: var(--card-border); box-shadow: none; border-radius: var(--card-border-radius); max-width: 640px; margin: var(--space-lg) auto; }
    .alert-message { font-size: 14px; line-height: 1.6; margin-bottom: var(--space-lg); }
    .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-sm); }
    .meta-item { display: flex; align-items: center; gap: var(--space-sm); font-size: 13px; }
    .meta-label { font-weight: 600; color: var(--color-text-muted); min-width: 100px; }
    .severity-info { color: var(--color-primary); }
    .severity-warning { color: var(--color-warning); }
    .severity-error, .severity-urgent { color: var(--color-error); }
    .severity-success { color: var(--color-success); }
  `],
})
export class AlertDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private notifSvc = inject(NotificationService);

  alert: AlertDetail | null = null;
  loading = true;
  loadError: string | null = null;

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.notifSvc.getAlert(id).subscribe((alert) => {
        this.alert = alert;
        this.loadError = alert ? null : 'This alert could not be loaded or no longer exists.';
        this.loading = false;
      });
    } else {
      this.loadError = 'This alert link is missing its ID.';
      this.loading = false;
    }
  }

  severityIcon(severity: string): string {
    const map: Record<string, string> = { info: 'info', success: 'check_circle', warning: 'warning', error: 'error', urgent: 'priority_high' };
    return map[severity] ?? 'notifications';
  }
}
