import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { PresenceService } from '../../../core/services/presence.service';

/**
 * Phase RC / Gap 139 — "N others viewing" badge.
 *
 * Sits in the toolbar. Hides itself when nobody else is online. The
 * count groups same-route peers separately ("3 others on Dashboard,
 * 2 elsewhere").
 *
 * Hover tooltip lists the usernames so the operator can spot a
 * teammate they didn't expect to be in.
 */
@Component({
  selector: 'app-presence-indicator',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    @if (peers().length > 0) {
      <span
        class="pi"
        [matTooltip]="tooltip()"
        matTooltipPosition="below"
        role="status"
        aria-live="polite"
      >
        <mat-icon class="pi-icon" aria-hidden="true">groups</mat-icon>
        <span class="pi-count">{{ peers().length }}</span>
        @if (sameRouteCount() > 0 && sameRouteCount() !== peers().length) {
          <span class="pi-here">· {{ sameRouteCount() }} here</span>
        }
      </span>
    }
  `,
  styles: [`
    .pi {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 12px;
      background: var(--color-success-light, rgba(30, 142, 62, 0.12));
      color: var(--color-success-dark, #137333);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .pi-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .pi-here { color: var(--color-text-secondary); }
  `],
})
export class PresenceIndicatorComponent {
  private readonly presence = inject(PresenceService);

  readonly peers = this.presence.peers;
  readonly sameRouteCount = computed(() => this.presence.peersOnSameRoute().length);

  readonly tooltip = computed(() => {
    const here = this.presence.peersOnSameRoute().map((p) => p.username);
    const elsewhere = this.presence
      .peers()
      .filter((p) => !this.presence.peersOnSameRoute().includes(p))
      .map((p) => p.username);
    const parts: string[] = [];
    if (here.length > 0) parts.push(`On this page: ${here.join(', ')}`);
    if (elsewhere.length > 0) parts.push(`Elsewhere in app: ${elsewhere.join(', ')}`);
    return parts.length > 0 ? parts.join(' · ') : 'No other users online';
  });
}
