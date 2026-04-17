import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DashboardData } from '../dashboard.service';

/**
 * Phase D1 / Gap 64 — "Today vs yesterday" trend deltas strip.
 *
 * A horizontal strip showing every key dashboard KPI with a colored
 * delta arrow. Operators glance at this and instantly see whether
 * things are trending the right way.
 *
 * Source data:
 *   - Today's values come from the standard `DashboardData`.
 *   - Yesterday's values are persisted client-side in localStorage
 *     keyed by `YYYY-MM-DD`. The first time a user opens the dashboard
 *     on a new day, today's values become the next day's "yesterday".
 *
 * This avoids a new backend endpoint while still giving real deltas.
 * A future session can promote yesterday-storage to the backend if
 * cross-device consistency matters.
 */

interface KpiTile {
  key: string;
  label: string;
  value: number;
  yesterday: number;
  /** When true, an INCREASE is bad (e.g. broken links). */
  inverted?: boolean;
  format?: (n: number) => string;
}

const STORAGE_KEY = 'xfil_dashboard_yesterday';

@Component({
  selector: 'app-trend-deltas',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule],
  template: `
    <mat-card class="td-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="td-avatar">trending_up</mat-icon>
        <mat-card-title>Today vs yesterday</mat-card-title>
        <mat-card-subtitle>How the key numbers moved overnight</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <div class="td-strip">
          @for (tile of tiles(); track tile.key) {
            <div class="td-tile" [matTooltip]="tooltipFor(tile)">
              <span class="td-label">{{ tile.label }}</span>
              <span class="td-value">{{ formatValue(tile) }}</span>
              <span class="td-delta" [class]="'td-' + verdictFor(tile)">
                <mat-icon class="td-arrow">{{ arrowFor(tile) }}</mat-icon>
                {{ deltaLabel(tile) }}
              </span>
            </div>
          }
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .td-card { width: 100%; }
    .td-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .td-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
    }
    .td-tile {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 10px 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .td-label {
      font-size: 11px;
      color: var(--color-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .td-value {
      font-size: 22px;
      font-weight: 500;
      color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
    }
    .td-delta {
      display: inline-flex;
      align-items: center;
      gap: 2px;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .td-good { color: var(--color-success, #1e8e3e); }
    .td-bad  { color: var(--color-error, #d93025); }
    .td-flat { color: var(--color-text-secondary); }
    .td-arrow {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
  `],
})
export class TrendDeltasComponent {
  /** Today's dashboard data. The component snapshots it for tomorrow. */
  @Input() set data(next: DashboardData | null | undefined) {
    this._data.set(next ?? null);
    if (next) this.snapshotForTomorrow(next);
  }

  /** Open broken links, fetched separately by the parent. */
  @Input() set openBrokenLinks(n: number | null | undefined) {
    this._brokenLinks.set(n ?? 0);
    if (this._data()) this.snapshotForTomorrow(this._data()!);
  }

  private readonly _data = signal<DashboardData | null>(null);
  private readonly _brokenLinks = signal<number>(0);
  private readonly _yesterday = signal<Record<string, number>>(this.readYesterday());

  readonly tiles = computed<readonly KpiTile[]>(() => {
    const data = this._data();
    if (!data) return [];
    const ystr = this._yesterday();
    return [
      {
        key: 'pending_reviews',
        label: 'Pending reviews',
        value: data.suggestion_counts?.pending ?? 0,
        yesterday: ystr['pending_reviews'] ?? 0,
      },
      {
        key: 'approved',
        label: 'Approved',
        value: data.suggestion_counts?.approved ?? 0,
        yesterday: ystr['approved'] ?? 0,
      },
      {
        key: 'applied',
        label: 'Applied',
        value: data.suggestion_counts?.applied ?? 0,
        yesterday: ystr['applied'] ?? 0,
      },
      {
        key: 'broken_links',
        label: 'Broken links',
        value: this._brokenLinks(),
        yesterday: ystr['broken_links'] ?? 0,
        inverted: true,
      },
      {
        key: 'content',
        label: 'Content items',
        value: data.content_count ?? 0,
        yesterday: ystr['content'] ?? 0,
      },
    ];
  });

  formatValue(tile: KpiTile): string {
    return tile.format ? tile.format(tile.value) : String(tile.value);
  }

  verdictFor(tile: KpiTile): 'good' | 'bad' | 'flat' {
    const diff = tile.value - tile.yesterday;
    if (diff === 0) return 'flat';
    const trendUp = diff > 0;
    // For inverted KPIs (broken links), an increase is bad.
    if (tile.inverted) return trendUp ? 'bad' : 'good';
    return trendUp ? 'good' : 'bad';
  }

  arrowFor(tile: KpiTile): string {
    const diff = tile.value - tile.yesterday;
    if (diff === 0) return 'remove';
    return diff > 0 ? 'arrow_upward' : 'arrow_downward';
  }

  deltaLabel(tile: KpiTile): string {
    const diff = tile.value - tile.yesterday;
    if (diff === 0) return 'unchanged';
    const sign = diff > 0 ? '+' : '';
    return `${sign}${diff}`;
  }

  tooltipFor(tile: KpiTile): string {
    return `Yesterday: ${tile.yesterday} · Today: ${tile.value}`;
  }

  // ── snapshot machinery ────────────────────────────────────────────

  /** Persist today's values under today's date. The next time the
   *  dashboard loads ON A DIFFERENT DAY, these become "yesterday". */
  private snapshotForTomorrow(data: DashboardData): void {
    try {
      const today = this.localDayKey();
      const raw = localStorage.getItem(STORAGE_KEY);
      const stash: Record<string, Record<string, number>> = raw
        ? JSON.parse(raw)
        : {};
      stash[today] = {
        pending_reviews: data.suggestion_counts?.pending ?? 0,
        approved: data.suggestion_counts?.approved ?? 0,
        applied: data.suggestion_counts?.applied ?? 0,
        broken_links: this._brokenLinks(),
        content: data.content_count ?? 0,
      };
      // Cap stash size — only keep the last 7 days.
      const days = Object.keys(stash).sort();
      while (days.length > 7) {
        const drop = days.shift();
        if (drop) delete stash[drop];
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stash));
    } catch {
      // No-op — worst case the user has no deltas this session.
    }
  }

  /** Read yesterday's snapshot. Returns empty object if unavailable. */
  private readYesterday(): Record<string, number> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const stash = JSON.parse(raw) as Record<string, Record<string, number>>;
      const yesterdayKey = this.yesterdayKey();
      return stash[yesterdayKey] ?? {};
    } catch {
      return {};
    }
  }

  private localDayKey(date: Date = new Date()): string {
    const y = date.getFullYear();
    const m = (date.getMonth() + 1).toString().padStart(2, '0');
    const d = date.getDate().toString().padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  private yesterdayKey(): string {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return this.localDayKey(d);
  }
}
