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
import { asyncScheduler, interval, merge, of, startWith, switchMap, throttleTime } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { RealtimeService } from '../../core/services/realtime.service';
import { ScrollAttentionService } from '../../core/services/scroll-attention.service';
import { applyDedup } from './mc-dedup';
import { McPayload, McTile } from './mc-types';
import { McTileComponent } from './mc-tile.component';
import { KernelListDialogComponent } from './kernel-list-dialog.component';

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

const PRIMARY_TILE_IDS = ['pipeline', 'signals', 'embeddings', 'cpp_hot_path'] as const;

@Component({
  selector: 'app-mission-critical',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    McTileComponent,
  ],
  template: `
    <section class="mc-tab">
      <!-- Primary stat card — 4 key tiles inline -->
      <mat-card class="mc-summary-card">
        <mat-card-header class="mc-summary-header">
          <span class="mc-summary-title">
            <mat-icon>dashboard_customize</mat-icon>
            Mission Critical
          </span>
          <div class="mc-health-pie" [matTooltip]="healthPieTooltip()" aria-hidden="true">
            @for (slice of healthPie(); track slice.state) {
              <span
                class="mc-pie-slice"
                [ngClass]="'mc-pie-' + slice.state.toLowerCase()"
                [style.flex]="slice.count"
              ></span>
            }
          </div>
          @if (loading()) {
            <mat-spinner diameter="16" matTooltip="Refreshing…" />
          }
        </mat-card-header>
        <mat-card-content>
          <div class="mc-stat-row">
            @for (tile of primaryTiles(); track tile.id) {
              <div class="mc-stat-tile" [attr.id]="'mc-tile-' + tile.id">
                <span class="mc-stat-dot" [ngClass]="'mc-dot-' + tile.state.toLowerCase()"></span>
                <div class="mc-stat-body">
                  <span class="mc-stat-name">{{ tile.name }}</span>
                  <span
                    class="mc-stat-msg"
                    [matTooltip]="tile.plain_english.length > 120 ? tile.plain_english : ''"
                  >{{ shortMsg(tile.plain_english) }}</span>
                  @if (tile.id === 'cpp_hot_path') {
                    <button
                      mat-button
                      color="primary"
                      class="mc-kernels-btn"
                      type="button"
                      (click)="openKernels(tile); $event.stopPropagation()"
                    >
                      See all kernels
                    </button>
                  }
                </div>
                <span
                  class="mc-state-chip"
                  [ngClass]="'mc-state-chip-' + tile.state.toLowerCase()"
                >{{ tile.state }}</span>
              </div>
            }
          </div>
        </mat-card-content>
      </mat-card>

      <!-- Algorithms summary or expanded tiles -->
      @if (grid().algorithmsSummary; as algo) {
        <section class="mc-algo-summary" [attr.aria-label]="algo.name">
          <mat-icon>auto_awesome</mat-icon>
          <span class="mc-algo-label">{{ algo.name }}</span>
          <span class="mc-algo-reason">{{ algo.plain_english }}</span>
        </section>
      }

      <!-- Remaining tiles grid (non-primary, non-algorithm-summary) -->
      <ul class="mc-grid" role="list">
        @for (tile of secondaryTiles(); track tile.id) {
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
        <footer class="mc-footer">Updated {{ relative(ts) }}</footer>
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
    /* ── Summary card ── */
    .mc-summary-card { border: var(--card-border); }
    .mc-summary-header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 16px 0;
    }
    .mc-summary-title {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
      font-weight: 500;
      flex: 1;
    }
    .mc-health-pie {
      display: inline-flex;
      height: 8px;
      min-width: 100px;
      border-radius: 4px;
      overflow: hidden;
      background: var(--color-bg-faint, #f1f3f4);
    }
    .mc-pie-slice { height: 100%; }
    .mc-pie-working  { background: var(--color-success, #1e8e3e); }
    .mc-pie-idle     { background: var(--color-text-secondary, #5f6368); opacity: 0.4; }
    .mc-pie-paused   { background: var(--color-primary, #1a73e8); }
    .mc-pie-degraded { background: var(--color-warning, #f9ab00); }
    .mc-pie-failed   { background: var(--color-error, #d93025); }
    /* ── 4-tile stat row ── */
    .mc-stat-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      padding: 12px 0 4px;
    }
    .mc-stat-tile {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 10px 12px;
      border-radius: 8px;
      border: var(--card-border);
      background: var(--color-bg-faint, #f8f9fa);
    }
    .mc-stat-dot {
      margin-top: 3px;
      flex-shrink: 0;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--color-text-secondary);
    }
    .mc-dot-working  { background: var(--color-success, #1e8e3e); }
    .mc-dot-idle     { background: var(--color-text-secondary, #5f6368); opacity: 0.5; }
    .mc-dot-paused   { background: var(--color-primary, #1a73e8); }
    .mc-dot-degraded { background: var(--color-warning, #f9ab00); }
    .mc-dot-failed   { background: var(--color-error, #d93025); }
    .mc-stat-body {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .mc-stat-name {
      font-size: 12px;
      font-weight: 600;
      color: var(--color-text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mc-stat-msg {
      font-size: 11px;
      color: var(--color-text-secondary);
      line-height: 1.4;
      /* Safety net in case shortMsg() can't run (e.g. server-side
         render) — cap at 3 visible lines, the rest is in the tooltip. */
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .mc-kernels-btn {
      font-size: 11px;
      padding: 0 4px;
      min-width: 0;
      line-height: 24px;
      height: 24px;
      margin-top: 2px;
    }
    .mc-state-chip {
      flex-shrink: 0;
      font-size: 9px;
      letter-spacing: 0.5px;
      padding: 2px 6px;
      border-radius: 10px;
      font-weight: 600;
      text-transform: uppercase;
      align-self: flex-start;
    }
    .mc-state-chip-working  { background: #e6f4ea; color: #137333; }
    .mc-state-chip-idle     { background: #f1f3f4; color: #5f6368; }
    .mc-state-chip-paused   { background: #e8f0fe; color: #1967d2; }
    .mc-state-chip-degraded { background: #fef7e0; color: #b06000; }
    .mc-state-chip-failed   { background: #fce8e6; color: #c5221f; }
    /* ── Algorithms summary ── */
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
    /* ── Secondary tiles grid ── */
    .mc-grid {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
    }
    .mc-cell { min-width: 0; }
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
  private dialog = inject(MatDialog);
  private scrollAttention = inject(ScrollAttentionService);
  private destroyRef = inject(DestroyRef);

  protected readonly loading = signal<boolean>(false);
  protected readonly tiles = signal<McTile[]>([]);
  protected readonly lastUpdated = signal<string | null>(null);

  private readonly alerted = new Set<string>();

  protected readonly grid = computed(() => applyDedup(this.tiles()));

  /** The 4 primary tiles shown inline in the summary card. */
  protected readonly primaryTiles = computed(() =>
    PRIMARY_TILE_IDS
      .map((id) => this.tiles().find((t) => t.id === id))
      .filter((t): t is McTile => t !== undefined),
  );

  /** All tiles NOT in the primary row — rendered in the secondary grid. */
  protected readonly secondaryTiles = computed(() =>
    this.grid().tiles.filter((t) => !(PRIMARY_TILE_IDS as readonly string[]).includes(t.id)),
  );

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
        // A burst of realtime pushes can fire one refresh per event.
        // `throttleTime` with leading + trailing surfaces the first
        // event immediately, suppresses the flood, then fires one
        // trailing refresh so the UI never gets stuck on stale data.
        // `debounceTime` would delay every refresh by 300 ms even when
        // events are rare — wrong shape. See docs/PERFORMANCE.md §13.
        throttleTime(300, asyncScheduler, { leading: true, trailing: true }),
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

  openKernels(tile: McTile): void {
    this.dialog.open(KernelListDialogComponent, {
      width: '480px',
      data: { kernels: tile.kernel_names ?? [], tileState: tile.state },
    });
  }

  onTileClick(tile: McTile): void {
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

  /**
   * Keep the inline summary-card stat tiles compact. The C++ hot path's
   * explanation can include every kernel name — without capping, the
   * .mc-stat-tile grows vertically to hundreds of pixels.
   */
  shortMsg(msg: string | null | undefined): string {
    if (!msg) return '';
    const LIMIT = 120;
    if (msg.length <= LIMIT) return msg;
    const hardCut = msg.slice(0, LIMIT);
    const lastSpace = hardCut.lastIndexOf(' ');
    const cut = lastSpace > LIMIT - 30 ? hardCut.slice(0, lastSpace) : hardCut;
    return cut.trim() + ' …';
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
