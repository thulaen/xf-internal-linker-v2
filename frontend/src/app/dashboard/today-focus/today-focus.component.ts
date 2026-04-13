import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

export interface TodayAction {
  title: string;
  reason: string;
  route: string;
  severity: 'info' | 'warning' | 'error';
  isBlocking: boolean;
  deepLinkTarget?: string;
}

@Component({
  selector: 'app-today-focus',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, MatButtonModule, EmptyStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="today-focus">
      <mat-card-header>
        <mat-icon mat-card-avatar>flag</mat-icon>
        <mat-card-title>Today's Focus</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (actions.length === 0) {
          <app-empty-state
            icon="check_circle"
            heading="Everything looks good!"
            body="No action items right now." />
        } @else {
          @for (a of actions; track a.title) {
            <div [class]="'action-row severity-' + a.severity">
              <mat-icon class="action-icon">{{ severityIcon(a.severity) }}</mat-icon>
              <div class="action-body">
                <span class="action-title">{{ a.title }}</span>
                <span class="action-reason">{{ a.reason }}</span>
              </div>
              <a mat-stroked-button
                 [routerLink]="a.route"
                 [fragment]="a.deepLinkTarget"
                 class="action-cta">View</a>
            </div>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .action-row {
      display: flex; align-items: center; gap: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-sm);
      margin-bottom: var(--space-sm);
    }
    .action-icon { flex-shrink: 0; }
    .action-body { flex: 1; display: flex; flex-direction: column; gap: var(--space-xs); }
    .action-title { font-weight: 500; font-size: 13px; color: var(--color-text-primary); }
    .action-reason { font-size: 12px; color: var(--color-text-secondary); }
    .action-cta { flex-shrink: 0; }
    .severity-info { background: var(--color-blue-50); }
    .severity-info .action-icon { color: var(--color-primary); }
    .severity-warning { background: var(--color-warning-light); }
    .severity-warning .action-icon { color: var(--color-warning); }
    .severity-error { background: var(--color-error-50); }
    .severity-error .action-icon { color: var(--color-error); }
  `],
})
export class TodayFocusComponent {
  @Input() actions: TodayAction[] = [];

  severityIcon(severity: string): string {
    switch (severity) {
      case 'error': return 'error';
      case 'warning': return 'warning';
      default: return 'info';
    }
  }
}
