import { ChangeDetectionStrategy, Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RealtimeService } from '../../../core/services/realtime.service';

/**
 * Phase GK2 / Gap 244 — Inline "reconnecting…" hint near any
 * realtime-fed component.
 *
 * Drop next to any live-updating card/list:
 *
 *   <h3>
 *     Jobs feed
 *     <app-reconnecting-hint />
 *   </h3>
 *
 * Subscribes to `RealtimeService.connectionStatus$` via toSignal so
 * the template reacts without leaking subscriptions. Renders nothing
 * when `connected`; an amber chip when `reconnecting`; a red chip
 * when `offline`.
 */
@Component({
  selector: 'app-reconnecting-hint',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    @switch (status()) {
      @case ('reconnecting') {
        <span
          class="rc-hint rc-reconnecting"
          role="status"
          aria-live="polite"
          [matTooltip]="tooltip || 'Live updates reconnecting — showing cached data.'"
        >
          <mat-icon class="rc-icon rc-spin">sync</mat-icon>
          Reconnecting…
        </span>
      }
      @case ('offline') {
        <span
          class="rc-hint rc-offline"
          role="status"
          aria-live="polite"
          [matTooltip]="tooltip || 'Live updates offline — showing cached data.'"
        >
          <mat-icon class="rc-icon">cloud_off</mat-icon>
          Offline
        </span>
      }
      @default { <!-- connected → render nothing --> }
    }
  `,
  styles: [`
    .rc-hint {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-left: 8px;
      padding: 2px 8px;
      font-size: 11px;
      border-radius: 12px;
      vertical-align: middle;
    }
    .rc-reconnecting {
      background: #fef7e0;
      color: #b06000;
    }
    .rc-offline {
      background: #fce8e6;
      color: #c5221f;
    }
    .rc-icon {
      width: 14px;
      height: 14px;
      font-size: 14px;
    }
    .rc-spin {
      animation: rc-spin 1.2s linear infinite;
    }
    @keyframes rc-spin {
      to { transform: rotate(360deg); }
    }
    @media (prefers-reduced-motion: reduce) {
      .rc-spin { animation: none; }
    }
  `],
})
export class ReconnectingHintComponent {
  @Input() tooltip = '';

  private realtime = inject(RealtimeService);
  protected readonly status = toSignal(this.realtime.connectionStatus$, {
    initialValue: 'connected' as const,
  });
}
