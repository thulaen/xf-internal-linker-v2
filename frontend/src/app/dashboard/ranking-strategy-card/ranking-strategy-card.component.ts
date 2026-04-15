import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';

@Component({
  selector: 'app-ranking-strategy-card',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, MatButtonModule, MatChipsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="ranking-strategy">
      <mat-card-header>
        <mat-icon mat-card-avatar>tune</mat-icon>
        <mat-card-title>Ranking Strategy</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="strategy-info">
          <mat-chip class="engine-chip" disableRipple>
            <mat-icon matChipAvatar>psychology</mat-icon>
            Auto-tuner (Python L-BFGS)
          </mat-chip>
        </div>
        @if (challengers.length > 0) {
          <div class="challengers">
            <span class="section-label">Challengers Active</span>
            @for (c of challengers; track $index) {
              <div class="challenger-row">
                <mat-icon class="challenger-icon">science</mat-icon>
                <span class="challenger-name">{{ c.name ?? 'Challenger ' + ($index + 1) }}</span>
                <span class="challenger-status">{{ c.status ?? 'running' }}</span>
              </div>
            }
          </div>
        } @else {
          <p class="no-challengers">No challengers running. The current weights are stable.</p>
        }
      </mat-card-content>
      <mat-card-actions align="end" class="dashboard-action-row">
        <a mat-stroked-button routerLink="/settings" fragment="ranking-weights">
          <mat-icon>settings</mat-icon> Adjust Weights
        </a>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .strategy-info { margin-bottom: var(--space-md); }
    .engine-chip {
      --mdc-chip-elevated-container-color: var(--color-blue-50);
      --mdc-chip-label-text-color: var(--color-primary);
    }
    .challengers { margin-top: var(--space-md); }
    .section-label {
      font-size: 12px; font-weight: 500;
      color: var(--color-text-muted);
      text-transform: uppercase; letter-spacing: 0.05em;
      margin-bottom: var(--space-sm); display: block;
    }
    .challenger-row {
      display: flex; align-items: center; gap: var(--space-sm);
      padding: var(--space-xs) 0;
    }
    .challenger-icon { color: var(--color-primary); font-size: 18px; width: 18px; height: 18px; }
    .challenger-name { flex: 1; font-size: 13px; color: var(--color-text-primary); }
    .challenger-status { font-size: 12px; color: var(--color-text-muted); }
    .no-challengers { font-size: 13px; color: var(--color-text-secondary); margin: 0; }
    mat-card-actions { padding: var(--space-md); }
  `],
})
export class RankingStrategyCardComponent {
  @Input() challengers: any[] = [];
}
