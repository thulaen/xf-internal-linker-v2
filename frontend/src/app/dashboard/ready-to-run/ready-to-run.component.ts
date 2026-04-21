import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-ready-to-run',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, MatButtonModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="ready-to-run">
      <mat-card-header>
        <mat-icon mat-card-avatar>{{ gateIcon }}</mat-icon>
        <mat-card-title>Pipeline Readiness</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div [class]="'gate-banner gate-' + gateLevel">
          <mat-icon>{{ gateIcon }}</mat-icon>
          <span class="gate-message">{{ gateMessage }}</span>
        </div>
        @if (blockers.length > 0) {
          <div class="blockers">
            @for (b of blockers; track b.label) {
              <div class="blocker-row">
                <mat-icon class="blocker-icon">{{ b.icon }}</mat-icon>
                <span class="blocker-label">{{ b.label }}</span>
                @if (b.route) {
                  <a mat-stroked-button
                     class="blocker-fix-btn"
                     [routerLink]="b.route"
                     [fragment]="b.fragment"
                     matTooltip="Jump to the fix"
                     matTooltipPosition="right">
                    <mat-icon>build</mat-icon>
                    <span>Fix</span>
                  </a>
                }
              </div>
            }
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .gate-banner {
      display: flex; align-items: center; gap: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-sm);
      font-size: 14px; font-weight: 500;
      margin-bottom: var(--space-md);
    }
    .gate-green { background: var(--color-success-light); color: var(--color-success-dark); }
    .gate-amber { background: var(--color-warning-light); color: var(--color-warning-dark); }
    .gate-red { background: var(--color-error-50); color: var(--color-error-dark); }
    .blockers { display: flex; flex-direction: column; gap: var(--space-sm); }
    /* Row layout: icon + label grow, Fix button pushes to the right edge so
       every row aligns the way the user expects. */
    .blocker-row {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .blocker-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
      color: var(--color-warning);
      flex-shrink: 0;
    }
    .blocker-label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .blocker-fix-btn {
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      height: 32px;
      line-height: 1;
    }
    .blocker-fix-btn mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
  `],
})
export class ReadyToRunComponent {
  @Input() health: { status: string } = { status: 'healthy' };
  @Input() lastRunDaysAgo: number | null = null;

  get gateLevel(): string {
    if (this.health.status === 'healthy' || this.health.status === 'warning') {
      return this.lastRunDaysAgo !== null && this.lastRunDaysAgo > 7 ? 'amber' : 'green';
    }
    return 'red';
  }

  get gateIcon(): string {
    if (this.gateLevel === 'green') return 'check_circle';
    if (this.gateLevel === 'amber') return 'warning';
    return 'error';
  }

  get gateMessage(): string {
    if (this.gateLevel === 'green') return 'Ready to run the pipeline.';
    if (this.gateLevel === 'amber') return 'Check a few things before running.';
    return 'Fix issues before running the pipeline.';
  }

  get blockers(): { label: string; icon: string; route?: string; fragment?: string }[] {
    const list: { label: string; icon: string; route?: string; fragment?: string }[] = [];
    if (this.health.status === 'error' || this.health.status === 'down') {
      list.push({ label: 'System health is degraded', icon: 'monitor_heart', route: '/health' });
    }
    if (this.lastRunDaysAgo !== null && this.lastRunDaysAgo > 7) {
      list.push({ label: `Last pipeline run was ${this.lastRunDaysAgo} days ago`, icon: 'schedule' });
    }
    if (this.health.status === 'stale') {
      list.push({ label: 'Data may be stale -- consider re-syncing', icon: 'sync_problem', route: '/jobs' });
    }
    return list;
  }
}
