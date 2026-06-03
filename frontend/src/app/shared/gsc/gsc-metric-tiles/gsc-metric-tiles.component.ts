import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

/** Fill colour for a metric tile. Maps to the GSC-measured series tokens. */
export type GscTileTone = 'blue' | 'purple' | 'green' | 'grey' | 'amber';

export interface GscTile {
  label: string;
  value: string | number;
  /** When set, the tile is filled with this colour + white text (GSC active-tile look). */
  tone?: GscTileTone;
}

/**
 * GSC primitive — metric tiles.
 *
 * The iconic Google Search Console metric-tile row: a joined, bordered,
 * 12px-rounded strip of tiles where each tile shows a label + a big number.
 * Tiles with a `tone` are filled with that series colour and use white text
 * (GSC's active "Total clicks" blue / "Total impressions" purple tiles);
 * tiles without a tone stay white with muted text (GSC's inactive tiles).
 *
 * Measured from live GSC (2026-05-30): tile min-width 180px, value 32px,
 * label 13px, fills = the `--series-*` tokens, white text on filled tiles.
 *
 * Usage:
 *   <app-gsc-metric-tiles [tiles]="[
 *     { label: 'Pending',  value: 5, tone: 'blue'  },
 *     { label: 'Approved', value: 3, tone: 'green' },
 *     { label: 'Total',    value: 8 }
 *   ]" />
 *
 * Design rules: tones are CSS classes (no inline style bindings — lint-safe);
 * all colours/sizes are tokens; OnPush.
 */
@Component({
  selector: 'app-gsc-metric-tiles',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="gsc-tiles">
      @for (t of tiles; track t.label) {
        <div
          class="gsc-tile"
          [class.tone-blue]="t.tone === 'blue'"
          [class.tone-purple]="t.tone === 'purple'"
          [class.tone-green]="t.tone === 'green'"
          [class.tone-grey]="t.tone === 'grey'"
          [class.tone-amber]="t.tone === 'amber'"
        >
          <span class="gsc-tile__label">{{ t.label }}</span>
          <span class="gsc-tile__value">{{ t.value }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .gsc-tiles {
      display: flex;
      flex-wrap: wrap;
      border: var(--card-border);
      border-radius: var(--card-border-radius);   /* 12px — GSC */
      overflow: hidden;
    }
    .gsc-tile {
      flex: 1;
      min-width: var(--gsc-metric-tile-min-w);     /* 180px — GSC measured */
      padding: var(--space-lg);                    /* 24px — matches GSC's ~110px tile height */
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
      border-left: var(--card-border);             /* thin divider between tiles */
    }
    .gsc-tile:first-child { border-left: 0; }
    .gsc-tile__label {
      font-size: var(--font-size-md);
      color: var(--color-text-muted);
    }
    .gsc-tile__value {
      font-size: var(--gsc-metric-value-size);     /* 32px — GSC measured */
      font-weight: 400;
      line-height: 1.2;
      color: var(--color-text-primary);
    }

    /* Filled tiles: series-colour background, white text, no divider line. */
    .gsc-tile.tone-blue   { background: var(--series-clicks); }
    .gsc-tile.tone-purple { background: var(--series-impressions); }
    .gsc-tile.tone-green  { background: var(--series-indexed); }
    .gsc-tile.tone-grey   { background: var(--series-not-indexed); }
    .gsc-tile.tone-amber  { background: var(--color-warning); }
    .gsc-tile[class*="tone-"] { border-left-color: transparent; }
    .gsc-tile[class*="tone-"] .gsc-tile__label { color: rgba(255, 255, 255, 0.9); }
    .gsc-tile[class*="tone-"] .gsc-tile__value { color: var(--color-text-on-dark); }
  `],
})
export class GscMetricTilesComponent {
  /** The tiles to render, left to right. */
  @Input() tiles: GscTile[] = [];
}
