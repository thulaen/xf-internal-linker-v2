import {
  ChangeDetectionStrategy,
  Component,
  Input,
  signal,
  computed,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Phase GK2 / Gap 252 — "Show raw data" debug toggle.
 *
 * Drop next to any chart or visualisation. Toggles between the chart
 * and a raw JSON peek of the `[data]` input. Power users can copy-paste
 * the JSON into a ticket or an AI prompt.
 *
 * Usage:
 *   <app-raw-data-toggle [data]="chartInput" label="Funnel chart">
 *     <ng-template #chart>
 *       <app-suggestion-funnel-chart [data]="chartInput" />
 *     </ng-template>
 *   </app-raw-data-toggle>
 *
 * Intentionally minimal — this is a developer affordance, not a
 * product feature. Styles match the app's existing JSON pane look.
 */
@Component({
  selector: 'app-raw-data-toggle',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="rdt-wrap">
      <div class="rdt-toggle-row">
        <button
          mat-icon-button
          type="button"
          class="rdt-toggle"
          (click)="toggle()"
          [matTooltip]="tooltip()"
          [attr.aria-pressed]="showRaw()"
          aria-label="Toggle raw data view"
        >
          <mat-icon>{{ showRaw() ? 'insights' : 'data_object' }}</mat-icon>
        </button>
      </div>
      @if (!showRaw()) {
        <ng-content />
      } @else {
        <pre class="rdt-json">{{ formatted() }}</pre>
      }
    </div>
  `,
  styles: [`
    .rdt-wrap { position: relative; }
    .rdt-toggle-row {
      display: flex;
      justify-content: flex-end;
    }
    .rdt-toggle {
      opacity: 0.6;
      transition: opacity 0.2s;
    }
    .rdt-toggle:hover,
    .rdt-toggle:focus-visible { opacity: 1; }
    .rdt-json {
      font-family: var(--font-mono);
      font-size: 12px;
      padding: 12px;
      margin: 0;
      max-height: 420px;
      overflow: auto;
      background: var(--color-bg-faint, #f8f9fa);
      border: 0.8px solid var(--color-border, #dadce0);
      border-radius: 4px;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--color-text-primary, #202124);
    }
  `],
})
export class RawDataToggleComponent {
  @Input() data: unknown = null;
  @Input() label = 'data';

  protected readonly showRaw = signal(false);
  protected readonly formatted = computed(() => {
    try {
      return JSON.stringify(this.data ?? null, null, 2);
    } catch {
      return '/* [unserialisable data] */';
    }
  });

  toggle(): void {
    this.showRaw.set(!this.showRaw());
  }

  tooltip(): string {
    return this.showRaw()
      ? `Show the ${this.label} chart`
      : `Show raw ${this.label} JSON`;
  }
}
