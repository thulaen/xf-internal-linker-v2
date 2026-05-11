import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';

/**
 * Challenger row shape — narrow enough for what this card renders.
 * Replaces a `: any[]` annotation flagged by the 2026-05-09 audit
 * (AutoIssue #21). Source-of-truth shape is the backend
 * RankingChallenger serializer; we re-declare a permissive subset here
 * to avoid a deep import that would couple this leaf component to the
 * settings module. No index signature: explicit fields keep dot-access
 * type-safe for the Angular template type-checker.
 */
export interface ChallengerRow {
  id?: number | string;
  name?: string;
  status?: string;
}

@Component({
  selector: 'app-ranking-strategy-card',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, MatButtonModule, MatChipsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="ranking-strategy">
      <mat-card-header>
        <mat-icon mat-card-avatar>tune</mat-icon>
        <mat-card-title i18n="@@dashboard.ranking.title">Ranking Strategy</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="strategy-header">
          <mat-chip class="engine-chip" disableRipple i18n="@@dashboard.ranking.engine">
            <mat-icon matChipAvatar>psychology</mat-icon>
            Auto-tuner (Python L-BFGS)
          </mat-chip>
          <a mat-stroked-button routerLink="/settings" fragment="ranking-weights">
            <mat-icon>settings</mat-icon>
            <span i18n="@@dashboard.ranking.btn.adjust">Adjust Weights</span>
          </a>
        </div>
        @if (challengers.length > 0) {
          <div class="challengers">
            <span class="section-label" i18n="@@dashboard.ranking.challengers.label">Challengers Active</span>
            @for (c of challengers; track $index) {
              <div class="challenger-row">
                <mat-icon class="challenger-icon">science</mat-icon>
                <span class="challenger-name">{{ getChallengerName(c, $index) }}</span>
                <span class="challenger-status">{{ c.status ?? 'running' }}</span>
              </div>
            }
          </div>
        } @else {
          <p class="no-challengers" i18n="@@dashboard.ranking.challengers.none">No challengers running. The current weights are stable.</p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .strategy-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      margin-bottom: var(--space-md);
    }
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
  `],
})
export class RankingStrategyCardComponent {
  @Input() challengers: ChallengerRow[] = [];

  getChallengerName(c: ChallengerRow, index: number): string {
    if (c.name) return c.name;
    const num = index + 1;
    return $localize`:@@dashboard.ranking.challenger.fallback:Challenger ${num}:index:`;
  }
}
