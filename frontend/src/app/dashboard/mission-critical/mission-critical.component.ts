import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, merge, of, startWith, switchMap } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { RealtimeService } from '../../core/services/realtime.service';
import { ScrollAttentionService } from '../../core/services/scroll-attention.service';
import { applyDedup } from './mc-dedup';
import { McPayload, McTile } from './mc-types';
import { McTileComponent } from './mc-tile.component';

/**
 * Phase MC — Mission Critical tab.
 *
 * Reads `/api/system/status/mission-critical/` (polls every 30s + on
 * realtime pushes). Applies client-side dedup so the main grid only
 * shows:
 *   • one row per root-cause (dependent tiles collapse under their root)
 *   • a single "Algorithms: all 5 healthy" summary when everything in
 *     the meta-algorithms group is green (expands only on degrade)
 *
 * Every FAILED tile triggers ScrollAttentionService.drawTo() on first
 * detection so the operator's eyes land on the broken thing.
 */
@Component({
  selector: 'app-mission-critical',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    McTileComponent,
  ],
  template: `
    <section class="mc-tab">
      <header class="mc-header">
        <h2 class="mc-title">
          <mat-icon>dashboard_customize</mat-icon>
          Mission Critical
        </h2>
        <p class="mc-subtitle">
          One glance at the pieces that actually have to work.
          Root causes shown once; healthy things are collapsed.
        </p>
        <!-- Phase MX1 / Gap 254 — health pie: visual summary of tile states. -->
        <div class="mc-health-pie" [matTooltip]="healthPieTooltip()" aria-hidden="true">
          @for (slice of healthPie(); track slice.state) {
            <span
              class="mc-pie-slice"
              [ngClass]="'mc-pie-' + slice.state.toLowerCase()"
              [style.flex]="slice.count"
              [attr.aria-label]="slice.count + ' ' + slice.state"
            ></span>
          }
        </div>
        <!-- Phase MX1 / Gap 264 — auto-refresh indicator. -->
        @if (loading()) {
          <mat-spinner diameter="18" matTooltip="Refreshing mission-critical state…" />
        }
      </header>

      @if (grid().algorithmsSummary; as algo) {
        <section class="mc-algo-summary" [attr.aria-label]="algo.name">
          <mat-icon>auto_awesome</mat-icon>
          <span class="mc-algo-label">{{ algo.name }}</span>
          <span class="mc-algo-reason">{{ algo.plain_english }}</span>
        </section>
      }

      <ul class="mc-grid" role="list">
        @for (tile of grid().tiles; track tile.id) {
          <li class="mc-cell" [attr.id]="'mc-tile-' + tile.id">
            <app-mc-tile
              [tile]="tile"
              [dependents]="grid().dependents[tile.id] || []"
              (tileClick)="onTileClick($event)"
              (action)="onAction($event)"
            />
          </li>
        }
      </ul>

      @if (lastUpdated(); as ts) {
        <footer class="mc-footer">
          Updated {{ relative(ts) }}
        </footer>
      }
    </section>
  `,
  styles: [`
    .mc-tab {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .mc-header {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .mc-title {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 18px;
      font-weight: 500;
    }
    .mc-subtitle {
      flex: 1;
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .mc-health-pie {
      display: inline-flex;
      height: 8px;
      min-width: 140px;
      border-radius: 4px;
      overflow: hidden;
      background: var(--color-bg-faint, #f1f3f4);
    }
    .mc-pie-slice { height: 100%; }
    .mc-pie-working { background: var(--color-success, #1e8e3e); }
    .mc-pie-idle    { background: var(--color-text-secondary, #5f6368); opacity: 0.4; }
    .mc-pie-paused  { background: var(--color-primary, #1a73e8); }
    .mc-pie-degraded{ background: var(--color-warning, #f9ab00); }
    .mc-pie-failed  { background: var(--color-error, #d93025); }
    .mc-algo-summary {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      border-radius: 4px;
      background: #e6f4ea;
      color: #137333;
      font-size: 13px;
    }
    .mc-algo-label { font-weight: 600; }
    .mc-algo-reason { color: #1e8e3e; }
    .mc-grid {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
    }
    .mc-cell {
      min-width: 0;
    }
    .mc-footer {
      font-size: 11px;
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
    }
  `],
})
export class MissionCriticalComponent implements OnInit {
  private http = inject(HttpClient);
  private realtime = inject(RealtimeService);
  private snack = inject(MatSnackBar);
  private scrollAttention = inject(ScrollAttentionService);
  private destroyRef = inject(DestroyRef);

  protected readonly loading = signal<boolean>(false);
  protected readonly tiles = signal<McTile[]>([]);
  protected readonly lastUpdated = signal<string | null>(null);

  /** Tracks which tile ids have already flashed scroll-attention,
   *  so we don't re-pulse the same failure on every refresh. */
  private readonly alerted = new Set<string>();

  /** Cached dedup result so the template doesn't recompute on each
   *  render — signals make this cheap; computed + Object.is equality
   *  covers the reference-change trigger. */
  protected readonly grid = computed(() => applyDedup(this.tiles()));

  /** Phase MX1 / Gap 254 — count tiles per state for the health pie.
   *  Order matters: WORKING/IDLE/PAUSED on the left, problems on the
   *  right so a red wedge is visually prominent. */
  protected readonly healthPie = computed(() => {
    const buckets = new Map<string, number>();
    for (const tile of this.tiles()) {
      buckets.set(tile.state, (buckets.get(tile.state) ?? 0) + 1);
    }
    const order = ['WORKING', 'IDLE', 'PAUSED', 'DEGRADED', 'FAILED'] as const;
    return order
      .map((state) => ({ state, count: buckets.get(state) ?? 0 }))
      .filter((s) => s.count > 0);
  });

  protected healthPieTooltip(): string {
    const pieces = this.healthPie().map(
      (s) => `${s.count} ${s.state.toLowerCase()}`,
    );
    return pieces.length ? `Health: ${pieces.join(' · ')}` : 'No tiles yet';
  }

  ngOnInit(): void {
    const realtimeNudge$ = this.realtime
      .subscribeTopic('mission_critical')
      .pipe(startWith(null));

    merge(
      interval(30_000).pipe(startWith(0)), // 30s polling floor
      realtimeNudge$,
    )
      .pipe(
        switchMap(() => {
          this.loading.set(true);
          return this.http
            .get<McPayload>('/api/system/status/mission-critical/')
            .pipe(catchError(() => of<McPayload | null>(null)));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((payload) => {
        this.loading.set(false);
        if (!payload) return;
        const next = payload.tiles || [];
        this.tiles.set(next);
        this.lastUpdated.set(payload.updated_at);
        this.flashNewFailures(next);
      });
  }

  onTileClick(tile: McTile): void {
    // Future: open a detail dialog. For now the scroll-to-attention
    // service pulses the tile itself so the user's eyes track it.
    this.scrollAttention.drawTo(`#mc-tile-${tile.id}`, {
      priority: tile.state === 'FAILED' ? 'urgent' : 'normal',
    });
  }

  onAction(payload: { tile: McTile; action: string }): void {
    // Placeholder wiring — a future pass will route each label to its
    // existing endpoint (resume/pause/recompute/etc). For now we just
    // acknowledge the intent so the button feels alive.
    this.snack.open(
      `“${payload.action}” requested for ${payload.tile.name}. ` +
        `(Endpoint wiring lands in the per-tile follow-up.)`,
      'OK',
      { duration: 3500 },
    );
  }

  relative(ts: string): string {
    const t = Date.parse(ts);
    if (Number.isNaN(t)) return '';
    const diff = Math.max(0, Date.now() - t);
    const s = Math.floor(diff / 1000);
    if (s < 5) return 'just now';
    if (s < 60) return `${s}s ago`;
    return `${Math.floor(s / 60)}m ago`;
  }

  private flashNewFailures(next: McTile[]): void {
    for (const tile of next) {
      if (tile.state !== 'FAILED') {
        this.alerted.delete(tile.id);
        continue;
      }
      if (this.alerted.has(tile.id)) continue;
      this.alerted.add(tile.id);
      // Defer so the DOM has rendered the tile before we attempt to
      // scroll it into view.
      queueMicrotask(() => {
        this.scrollAttention.drawTo(`#mc-tile-${tile.id}`, {
          priority: 'urgent',
        });
      });
    }
  }
}
