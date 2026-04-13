import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-freshness-badge',
  standalone: true,
  imports: [MatChipsModule, MatIconModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-chip
      [class]="'freshness-chip freshness-' + level"
      [matTooltip]="tooltip"
      disableRipple
    >
      <mat-icon matChipAvatar class="freshness-icon">{{ icon }}</mat-icon>
      {{ label }}
    </mat-chip>
  `,
  styles: [`
    .freshness-chip {
      font-size: 12px;
      height: 28px;
    }
    .freshness-icon { font-size: 16px; width: 16px; height: 16px; }
    .freshness-fresh {
      --mdc-chip-elevated-container-color: var(--color-success-light);
      --mdc-chip-label-text-color: var(--color-success-dark);
    }
    .freshness-stale {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .freshness-expired {
      --mdc-chip-elevated-container-color: var(--color-error-50);
      --mdc-chip-label-text-color: var(--color-error-dark);
    }
  `],
})
export class FreshnessBadgeComponent {
  @Input() updatedAt: string | Date | null = null;
  @Input() staleAfterHours = 24;

  get hoursAgo(): number | null {
    if (!this.updatedAt) return null;
    const then = new Date(this.updatedAt).getTime();
    if (isNaN(then)) return null;
    return Math.floor((Date.now() - then) / 3_600_000);
  }

  get level(): 'fresh' | 'stale' | 'expired' {
    const h = this.hoursAgo;
    if (h === null) return 'expired';
    if (h <= this.staleAfterHours) return 'fresh';
    if (h <= this.staleAfterHours * 3) return 'stale';
    return 'expired';
  }

  get label(): string {
    const h = this.hoursAgo;
    if (h === null) return 'Never synced';
    if (h < 1) return 'Updated just now';
    if (h < 24) return `Updated ${h}h ago`;
    const days = Math.floor(h / 24);
    return `${days}d ago`;
  }

  get icon(): string {
    if (this.level === 'fresh') return 'check_circle';
    if (this.level === 'stale') return 'schedule';
    return 'error_outline';
  }

  get tooltip(): string {
    if (this.level === 'fresh') return 'Data is up to date';
    if (this.level === 'stale') return 'Data may be stale — consider re-syncing';
    return 'Data is outdated or has never been synced';
  }
}
