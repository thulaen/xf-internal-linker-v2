import { ChangeDetectionStrategy, Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D3 / Gaps 158 + 170 — combined "Launcher Grid".
 *
 * Six big friendly tiles linking to the most common landing pages.
 * Distinct from the sidenav (which is a list of every page) — this
 * is the noob-friendly "I don't know what to click" entry point that
 * surfaces only the highest-traffic destinations with oversized
 * icons and one-word labels.
 *
 * Both Gap 158 ("don't know what to click" launcher) and Gap 170
 * ("six-tile big-icon launcher grid") describe the same surface;
 * splitting them would be redundant. The "I don't know what to click"
 * subtitle wording satisfies Gap 158's framing while the 6-tile
 * layout satisfies Gap 170.
 */

interface Tile {
  label: string;
  hint: string;
  icon: string;
  route: string;
  fragment?: string;
}

const TILES: readonly Tile[] = [
  { label: 'Review', hint: 'Approve link suggestions', icon: 'rate_review', route: '/review' },
  { label: 'Health', hint: 'Check service status', icon: 'health_and_safety', route: '/health' },
  { label: 'Jobs', hint: 'Imports & pipeline runs', icon: 'pending_actions', route: '/jobs' },
  { label: 'Alerts', hint: 'Read what fired', icon: 'notifications', route: '/alerts' },
  { label: 'Graph', hint: 'See your link network', icon: 'account_tree', route: '/graph' },
  { label: 'Settings', hint: 'Tune & configure', icon: 'settings', route: '/settings' },
];

@Component({
  selector: 'app-launcher-grid',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, RouterLink, MatCardModule, MatIconModule],
  template: `
    <mat-card class="lg-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="lg-avatar">apps</mat-icon>
        <mat-card-title>Not sure what to click?</mat-card-title>
        <mat-card-subtitle>Pick one of the six common destinations</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <ul class="lg-grid">
          @for (tile of tiles; track tile.label) {
            <li>
              <a
                class="lg-tile"
                [routerLink]="tile.route"
                [fragment]="tile.fragment ?? undefined"
              >
                <mat-icon class="lg-tile-icon" aria-hidden="true">{{ tile.icon }}</mat-icon>
                <span class="lg-tile-label">{{ tile.label }}</span>
                <span class="lg-tile-hint">{{ tile.hint }}</span>
              </a>
            </li>
          }
        </ul>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .lg-card { height: 100%; }
    .lg-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .lg-grid {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    @media (max-width: 480px) {
      .lg-grid { grid-template-columns: repeat(2, 1fr); }
    }
    .lg-tile {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 16px 12px;
      text-decoration: none;
      color: var(--color-text-primary);
      background: var(--color-bg-faint);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      transition: background-color 0.15s ease, transform 0.15s ease, border-color 0.15s ease;
      text-align: center;
    }
    .lg-tile:hover,
    .lg-tile:focus-visible {
      background: var(--color-bg-white);
      border-color: var(--color-primary);
      transform: translateY(-2px);
    }
    .lg-tile:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    .lg-tile-icon {
      font-size: 32px;
      width: 32px;
      height: 32px;
      color: var(--color-primary);
    }
    .lg-tile-label {
      font-weight: 500;
      font-size: 13px;
    }
    .lg-tile-hint {
      font-size: 11px;
      color: var(--color-text-secondary);
      line-height: 1.3;
    }
    @media (prefers-reduced-motion: reduce) {
      .lg-tile { transition: none; }
      .lg-tile:hover, .lg-tile:focus-visible { transform: none; }
    }
  `],
})
export class LauncherGridComponent {
  readonly tiles = TILES;
}
