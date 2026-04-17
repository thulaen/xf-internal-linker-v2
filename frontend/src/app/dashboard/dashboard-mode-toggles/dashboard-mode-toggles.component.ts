import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DashboardModesService } from '../../core/services/dashboard-modes.service';

/**
 * Phase D3 — visible buttons for the two dashboard modes:
 *   - Gap 161 Safe Mode toggle
 *   - Gap 167 Calm Mode toggle
 *
 * Lives in the dashboard hero so the operator sees both states from
 * the moment they land. Service handles persistence.
 */
@Component({
  selector: 'app-dashboard-mode-toggles',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="dmt-row" role="group" aria-label="Dashboard modes">
      <button
        mat-stroked-button
        type="button"
        class="dmt-btn"
        [class.dmt-on]="modes.safe()"
        [matTooltip]="modes.safe() ? 'Safe mode is ON — write actions are disabled' : 'Turn on safe mode (read-only writes off)'"
        [attr.aria-pressed]="modes.safe()"
        (click)="modes.toggleSafe()"
      >
        <mat-icon>{{ modes.safe() ? 'lock' : 'lock_open' }}</mat-icon>
        Safe mode
      </button>
      <button
        mat-stroked-button
        type="button"
        class="dmt-btn"
        [class.dmt-on]="modes.calm()"
        [matTooltip]="modes.calm() ? 'Calm mode is ON — non-essential cards hidden' : 'Turn on calm mode (focus view)'"
        [attr.aria-pressed]="modes.calm()"
        (click)="modes.toggleCalm()"
      >
        <mat-icon>{{ modes.calm() ? 'spa' : 'self_improvement' }}</mat-icon>
        Calm mode
      </button>
    </div>
  `,
  styles: [`
    .dmt-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .dmt-btn {
      transition: background-color 0.15s ease, color 0.15s ease;
    }
    .dmt-on {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .dmt-on mat-icon { color: var(--color-on-primary, #ffffff); }
    @media (prefers-reduced-motion: reduce) {
      .dmt-btn { transition: none; }
    }
  `],
})
export class DashboardModeTogglesComponent {
  readonly modes = inject(DashboardModesService);
}
