import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RecentPagesService } from '../../../core/services/recent-pages.service';

/**
 * Phase NV / Gap 146 — Recent pages menu.
 *
 * Toolbar icon-button that opens a small Material menu listing the last
 * 5 pages the user visited (excluding the current one). Each item is a
 * routerLink that navigates back; the relative time of the visit is
 * shown beside the label so the user can orient themselves quickly.
 *
 * The menu is automatically hidden when there's nothing to show — no
 * empty-state to clutter the toolbar.
 */
@Component({
  selector: 'app-recent-pages-menu',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  template: `
    @if (svc.menuPages().length > 0) {
      <button
        mat-icon-button
        type="button"
        [matMenuTriggerFor]="menu"
        matTooltip="Recently visited pages"
        matTooltipPosition="below"
        aria-label="Open recent pages menu"
      >
        <mat-icon>history</mat-icon>
      </button>
      <mat-menu #menu="matMenu" class="ga4-menu" xPosition="before">
        <div class="rp-header" (click)="$event.stopPropagation()">
          Recent pages
        </div>
        @for (p of svc.menuPages(); track p.url) {
          <a
            mat-menu-item
            [routerLink]="p.url"
            class="rp-item"
          >
            <mat-icon>schedule</mat-icon>
            <span class="rp-label">{{ p.label }}</span>
            <span class="rp-time">{{ relative(p.visitedAt) }}</span>
          </a>
        }
        <button
          mat-menu-item
          type="button"
          class="rp-clear"
          (click)="svc.clear()"
        >
          <mat-icon>delete_outline</mat-icon>
          Clear history
        </button>
      </mat-menu>
    }
  `,
  styles: [`
    .rp-header {
      padding: 8px 16px 4px;
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.4px;
      text-transform: uppercase;
      color: var(--color-text-secondary, #5f6368);
      pointer-events: none;
    }
    .rp-item {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .rp-label {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .rp-time {
      margin-left: 16px;
      font-size: 11px;
      color: var(--color-text-secondary, #5f6368);
      font-variant-numeric: tabular-nums;
    }
    .rp-clear { color: var(--color-text-secondary, #5f6368); }
  `],
})
export class RecentPagesMenuComponent {
  protected svc = inject(RecentPagesService);

  /** Tiny inline relative-time formatter (no Intl call per row). */
  protected relative(ts: number): string {
    const diff = Math.max(0, Date.now() - ts);
    const s = Math.floor(diff / 1000);
    if (s < 60) return 'just now';
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  }
}
