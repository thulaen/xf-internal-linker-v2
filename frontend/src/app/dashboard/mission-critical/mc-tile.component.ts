import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { McTile } from './mc-types';

/**
 * Phase MC — single tile. All behavior is parent-driven:
 *   • clicks emit (tileClick) — parent scrolls to the detail panel
 *     (via the Gap 148 Scroll-to-Attention service) and opens it.
 *   • action-button clicks emit (action) with the label — parent
 *     routes to the right endpoint (resume/pause/reconnect/etc).
 */
@Component({
  selector: 'app-mc-tile',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressBarModule,
    MatTooltipModule,
  ],
  template: `
    <mat-card
      class="mc-tile"
      [ngClass]="'mc-state-' + tile.state.toLowerCase()"
      role="button"
      tabindex="0"
      (click)="tileClick.emit(tile)"
      (keydown.enter)="tileClick.emit(tile)"
      (keydown.space)="tileClick.emit(tile); $event.preventDefault()"
      [attr.aria-label]="tile.name + ': ' + tile.state"
    >
      <mat-card-header class="mc-head">
        <span class="mc-dot" [ngClass]="'mc-dot-' + tile.state.toLowerCase()"></span>
        <span class="mc-name">{{ tile.name }}</span>
        <span class="mc-state-chip" [ngClass]="'mc-state-chip-' + tile.state.toLowerCase()">
          {{ tile.state }}
        </span>
      </mat-card-header>
      <mat-card-content>
        <p class="mc-msg">{{ tile.plain_english }}</p>
        @if (tile.progress !== null && tile.progress !== undefined) {
          <mat-progress-bar
            mode="determinate"
            [value]="tile.progress * 100"
          />
        }
        <!-- Phase MX1 — Gap 255 ETA + Gap 256 last-action subtitle. -->
        @if (tile.eta_seconds || tile.last_action_label) {
          <p class="mc-meta">
            @if (tile.eta_seconds) {
              <span class="mc-meta-chip" [matTooltip]="'Estimated time to completion'">
                <mat-icon inline>timer</mat-icon>
                ETA {{ formatEta(tile.eta_seconds) }}
              </span>
            }
            @if (tile.last_action_label) {
              <span class="mc-meta-chip mc-meta-muted">
                {{ tile.last_action_label }}
              </span>
            }
          </p>
        }
        <!-- Phase MX1 — Gap 257 uptime + Gap 262 grade + Gap 261 retries + Gap 265 silent-since. -->
        @if (tile.uptime_pct_24h !== null && tile.uptime_pct_24h !== undefined) {
          <div class="mc-badges">
            <span class="mc-badge" matTooltip="24-hour uptime percentage">
              ↑ {{ tile.uptime_pct_24h }}%
            </span>
            @if (tile.health_grade) {
              <span
                class="mc-badge mc-grade"
                [ngClass]="'mc-grade-' + tile.health_grade.toLowerCase()"
                matTooltip="Health grade over the last 24 hours"
              >
                {{ tile.health_grade }}
              </span>
            }
            @if (tile.retry_count_since_success && tile.retry_count_since_success > 0) {
              <span
                class="mc-badge mc-retry"
                matTooltip="Retries since last success"
              >
                × {{ tile.retry_count_since_success }}
              </span>
            }
            @if (tile.silent_since) {
              <span class="mc-badge mc-silent" [matTooltip]="'Silent since ' + tile.silent_since">
                <mat-icon inline>volume_off</mat-icon>
                silent
              </span>
            }
          </div>
        }
        <!-- Phase MX1 — Gap 260 downstream impact preview. -->
        @if (tile.downstream_impact && tile.downstream_impact.length > 0) {
          <p class="mc-downstream" [matTooltip]="'Features that degrade if this fails'">
            <mat-icon inline>warning_amber</mat-icon>
            Impacts: {{ tile.downstream_impact.join(', ') }}
          </p>
        }
        @if (dependents && dependents.length > 0) {
          <p class="mc-affects">
            <mat-icon inline>link</mat-icon>
            Affected: {{ affectedSummary(dependents) }}
          </p>
        }
      </mat-card-content>
      @if (tile.actions.length > 0) {
        <mat-card-actions class="mc-actions" (click)="$event.stopPropagation()">
          @for (a of tile.actions; track a) {
            <button
              mat-button
              color="primary"
              type="button"
              (click)="action.emit({ tile: tile, action: a })"
              [matTooltip]="tooltipFor(a)"
            >
              {{ a }}
            </button>
          }
        </mat-card-actions>
      }
    </mat-card>
  `,
  styles: [`
    :host { display: block; }
    .mc-tile {
      padding: 12px;
      cursor: pointer;
      transition: box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .mc-tile:hover {
      box-shadow: var(--shadow-md, 0 2px 6px rgba(60,64,67,0.15));
    }
    .mc-tile:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    .mc-head {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0;
    }
    .mc-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--color-text-secondary);
    }
    .mc-dot-working { background: var(--color-success, #1e8e3e); }
    .mc-dot-idle    { background: var(--color-text-secondary, #5f6368); }
    .mc-dot-paused  { background: var(--color-primary, #1a73e8); }
    .mc-dot-degraded{ background: var(--color-warning, #f9ab00); }
    .mc-dot-failed  { background: var(--color-error, #d93025); }
    .mc-name {
      flex: 1;
      font-weight: 500;
      font-size: 14px;
      color: var(--color-text-primary);
    }
    .mc-state-chip {
      font-size: 10px;
      letter-spacing: 0.5px;
      padding: 2px 8px;
      border-radius: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .mc-state-chip-working  { background: #e6f4ea; color: #137333; }
    .mc-state-chip-idle     { background: #f1f3f4; color: #5f6368; }
    .mc-state-chip-paused   { background: #e8f0fe; color: #1967d2; }
    .mc-state-chip-degraded { background: #fef7e0; color: #b06000; }
    .mc-state-chip-failed   { background: #fce8e6; color: #c5221f; }
    .mc-msg {
      margin: 8px 0 0;
      font-size: 12px;
      color: var(--color-text-primary);
      word-break: break-word;
    }
    .mc-affects {
      margin: 8px 0 0;
      font-size: 11px;
      color: var(--color-text-secondary);
      font-style: italic;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .mc-actions {
      display: flex;
      justify-content: flex-end;
      padding: 4px 0 0;
    }
    mat-progress-bar {
      margin-top: 8px;
    }
    .mc-meta {
      margin: 8px 0 0;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      font-size: 11px;
    }
    .mc-meta-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 1px 6px;
      background: var(--color-bg-faint, #f1f3f4);
      border-radius: 10px;
      color: var(--color-text-primary, #202124);
    }
    .mc-meta-muted { color: var(--color-text-secondary, #5f6368); }
    .mc-badges {
      margin-top: 8px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .mc-badge {
      font-size: 11px;
      padding: 1px 6px;
      border-radius: 10px;
      background: var(--color-bg-faint, #f1f3f4);
      color: var(--color-text-secondary, #5f6368);
      font-variant-numeric: tabular-nums;
    }
    .mc-grade { font-weight: 700; }
    .mc-grade-a { background: #e6f4ea; color: #137333; }
    .mc-grade-b { background: #e8f0fe; color: #1967d2; }
    .mc-grade-c { background: #fef7e0; color: #b06000; }
    .mc-grade-d { background: #fce8e6; color: #c5221f; }
    .mc-grade-f { background: #fce8e6; color: #c5221f; font-weight: 900; }
    .mc-retry { background: #fef7e0; color: #b06000; }
    .mc-silent {
      background: #fce8e6;
      color: #c5221f;
      display: inline-flex;
      align-items: center;
      gap: 2px;
    }
    .mc-downstream {
      margin: 6px 0 0;
      font-size: 11px;
      font-style: italic;
      color: var(--color-text-secondary, #5f6368);
      display: flex;
      align-items: center;
      gap: 4px;
    }
  `],
})
export class McTileComponent {
  @Input({ required: true }) tile!: McTile;
  @Input() dependents: McTile[] = [];

  @Output() tileClick = new EventEmitter<McTile>();
  @Output() action = new EventEmitter<{ tile: McTile; action: string }>();

  affectedSummary(deps: McTile[]): string {
    return deps.map((d) => d.name).join(', ');
  }

  /** Phase MX1 / Gap 255 — compact ETA formatter ("2m 14s" / "~1h"). */
  formatEta(seconds: number): string {
    if (!Number.isFinite(seconds) || seconds <= 0) return '—';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) {
      const m = Math.floor(seconds / 60);
      const s = Math.round(seconds - m * 60);
      return s === 0 ? `${m}m` : `${m}m ${s}s`;
    }
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds - h * 3600) / 60);
    return m === 0 ? `~${h}h` : `${h}h ${m}m`;
  }

  tooltipFor(label: string): string {
    switch (label) {
      case 'Pause': return 'Pause this component at the next safe checkpoint';
      case 'Resume': return 'Resume from checkpoint';
      case 'Reconnect': return 'Re-run the connector auth flow';
      case 'Rebuild': return 'Trigger a full rebuild';
      case 'Recompute': return 'Trigger a recompute';
      case 'Run now': return 'Run this algorithm now (gated by sequential lock)';
      default: return '';
    }
  }
}
