import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-runtime-mode',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, MatButtonModule, MatChipsModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="runtime-mode">
      <mat-card-header>
        <mat-icon mat-card-avatar>memory</mat-icon>
        <mat-card-title>Runtime</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="runtime-row">
          <div class="mode-display">
            <mat-chip [class]="'mode-chip mode-' + mode" disableRipple>
              <mat-icon matChipAvatar>{{ modeIcon }}</mat-icon>
              {{ modeLabel }}
            </mat-chip>
            @if (mode === 'warming') {
              <span class="warming-hint">GPU is warming up. This usually takes a minute or two.</span>
            }
          </div>
          <a mat-stroked-button
             class="runtime-adjust-btn"
             routerLink="/dashboard"
             fragment="performance-mode"
             matTooltip="Jump to the Performance Mode card to switch Safe / Balanced / High Performance"
             aria-label="Adjust Performance Mode">
            <mat-icon>tune</mat-icon>
            <span>Adjust Mode</span>
          </a>
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    /* The chip + Adjust Mode button sit side-by-side when there's room.
       In a narrow grid cell the button was being squeezed down to ~68px
       wide and visually overlapping the chip. flex-wrap lets the row
       cleanly stack: chip on the first line, button on the second, if
       there isn't horizontal space. (User feedback 2026-04-20.) */
    .runtime-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: var(--space-md);
    }
    .mode-display { display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap; min-width: 0; }
    .mode-chip {
      --mdc-chip-elevated-container-color: var(--color-bg-faint);
      --mdc-chip-label-text-color: var(--color-text-primary);
      font-weight: 500;
    }
    .mode-cpu {
      --mdc-chip-elevated-container-color: var(--color-blue-50);
      --mdc-chip-label-text-color: var(--color-primary);
    }
    .mode-gpu {
      --mdc-chip-elevated-container-color: var(--color-success-light);
      --mdc-chip-label-text-color: var(--color-success-dark);
    }
    .mode-warming {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .warming-hint { font-size: 12px; color: var(--color-text-muted); }
    /* Keep the action label on one line even in narrow cards — no awkward mid-word wrap. */
    .runtime-adjust-btn {
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
    }
    .runtime-adjust-btn span {
      white-space: nowrap;
    }
  `],
})
export class RuntimeModeComponent {
  @Input() mode = 'cpu';

  get modeIcon(): string {
    if (this.mode === 'gpu') return 'developer_board';
    if (this.mode === 'warming') return 'hourglass_top';
    return 'memory';
  }

  get modeLabel(): string {
    if (this.mode === 'gpu') return 'GPU Active';
    if (this.mode === 'warming') return 'GPU Warming Up';
    return 'CPU Mode';
  }
}
