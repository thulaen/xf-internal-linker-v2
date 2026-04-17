import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { BehaviorTrackerService } from '../../core/services/behavior-tracker.service';

/**
 * Phase D2 / Gap 73 — Behavioral Nudge card.
 *
 * Shows a short suggestion based on the user's recent navigation
 * habits: "Yesterday you usually checked Alerts first." Helps noobs
 * build a routine and reminds returning users where they left off.
 *
 * Hidden entirely when there's not enough history (≥ 3 days). Reads
 * client-only data from BehaviorTrackerService — no network call, no
 * server-side profiling.
 */

const ROUTE_LABELS: Record<string, { label: string; icon: string }> = {
  '/alerts': { label: 'Alerts page', icon: 'notifications' },
  '/health': { label: 'System Health page', icon: 'health_and_safety' },
  '/jobs': { label: 'Jobs page', icon: 'pending_actions' },
  '/review': { label: 'Review queue', icon: 'rate_review' },
  '/link-health': { label: 'Link Health page', icon: 'link_off' },
  '/graph': { label: 'Link Graph', icon: 'account_tree' },
  '/analytics': { label: 'Analytics page', icon: 'bar_chart' },
  '/behavioral-hubs': { label: 'Behavioral Hubs', icon: 'hub' },
  '/settings': { label: 'Settings', icon: 'settings' },
  '/error-log': { label: 'Error Log', icon: 'bug_report' },
  '/performance': { label: 'Performance benchmarks', icon: 'speed' },
  '/crawler': { label: 'Web Crawler', icon: 'travel_explore' },
};

@Component({
  selector: 'app-behavioral-nudge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
  ],
  template: `
    @if (suggestion(); as s) {
      <mat-card class="bn-card">
        <mat-card-header>
          <mat-icon mat-card-avatar class="bn-avatar">history</mat-icon>
          <mat-card-title>Pick up where you usually start</mat-card-title>
          <mat-card-subtitle>
            Based on your last {{ s.days }} day{{ s.days === 1 ? '' : 's' }}
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="bn-text">
            You typically open the
            <strong>{{ s.label }}</strong>
            first thing — {{ s.count }} of the last {{ s.days }} days.
          </p>
        </mat-card-content>
        <mat-card-actions>
          <a
            mat-flat-button
            color="primary"
            [routerLink]="s.route"
          >
            <mat-icon>{{ s.icon }}</mat-icon>
            Open {{ s.label }}
          </a>
        </mat-card-actions>
      </mat-card>
    }
  `,
  styles: [`
    .bn-card { height: 100%; }
    .bn-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .bn-text {
      margin: 0;
      font-size: 14px;
      line-height: 1.55;
      color: var(--color-text-primary);
    }
  `],
})
export class BehavioralNudgeComponent implements OnInit {
  private readonly tracker = inject(BehaviorTrackerService);

  readonly suggestion = signal<{
    route: string;
    label: string;
    icon: string;
    count: number;
    days: number;
  } | null>(null);

  ngOnInit(): void {
    const data = this.tracker.getMostVisitedRoute();
    if (!data) return;
    const meta = ROUTE_LABELS[data.route];
    if (!meta) return;
    this.suggestion.set({
      route: data.route,
      label: meta.label,
      icon: meta.icon,
      count: data.count,
      days: data.days,
    });
  }
}
