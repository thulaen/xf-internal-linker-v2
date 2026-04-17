import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  inject,
  Input,
  Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { SuggestionReadinessService } from '../../core/services/suggestion-readiness.service';

/**
 * Phase SR — "Preparing Suggestions" panel shown while the readiness
 * gate reports at least one blocking prerequisite.
 *
 * Renders the plain-English prerequisite list with per-row status icon
 * + progress bar + next step. Matches the UX of the Preference Center's
 * onboarding panel so noobs recognise the pattern.
 *
 * The gate parent (`ReviewComponent`) controls visibility. This
 * component is pure presentation + one optional escape-hatch button
 * the operator can use to override the gate for their session.
 */
@Component({
  selector: 'app-preparing-suggestions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatTooltipModule,
  ],
  template: `
    <section class="ps-panel" role="status" aria-live="polite">
      <header class="ps-header">
        <mat-icon class="ps-header-icon">hourglass_empty</mat-icon>
        <div>
          <h2 class="ps-title">Preparing suggestions…</h2>
          <p class="ps-subtitle">
            Holding back results until every source is ready — no
            half-computed rows.
          </p>
        </div>
      </header>

      @if (readiness.blocking().length > 0) {
        <ul class="ps-list">
          @for (p of readiness.blocking(); track p.id) {
            <li class="ps-row">
              <span class="ps-row-icon" [ngClass]="'ps-' + p.status">
                <mat-icon>{{ iconFor(p.status) }}</mat-icon>
              </span>
              <div class="ps-row-body">
                <div class="ps-row-head">
                  <span class="ps-row-name">{{ p.name }}</span>
                  <span class="ps-row-chip" [ngClass]="'ps-' + p.status">
                    {{ labelFor(p.status) }}
                  </span>
                </div>
                <p class="ps-row-reason">{{ p.plain_english }}</p>
                @if (p.next_step) {
                  <p class="ps-row-next">
                    <mat-icon inline>lightbulb</mat-icon>
                    {{ p.next_step }}
                  </p>
                }
                @if (p.status === 'running' && p.progress > 0) {
                  <mat-progress-bar
                    mode="determinate"
                    [value]="p.progress * 100"
                  />
                }
                @if (p.affects.length > 0) {
                  <p class="ps-row-affects">
                    <mat-icon inline>link</mat-icon>
                    Also affects:
                    <span
                      *ngFor="let a of p.affects; let last = last"
                      class="ps-affects-item"
                    >{{ a }}<span *ngIf="!last">, </span></span>
                  </p>
                }
              </div>
            </li>
          }
        </ul>
      } @else if (readiness.loading()) {
        <p class="ps-loading">Checking readiness…</p>
      }

      @if (allowOverride) {
        <div class="ps-actions">
          <button
            mat-button
            color="warn"
            type="button"
            (click)="override.emit()"
            matTooltip="Show suggestions anyway (results may be stale)"
          >
            <mat-icon>visibility</mat-icon>
            Show me anyway
          </button>
        </div>
      }
    </section>
  `,
  styles: [`
    .ps-panel {
      max-width: 780px;
      margin: 32px auto;
      padding: 24px;
      background: var(--color-bg-faint, #f8f9fa);
      border: var(--card-border, 0.8px solid #dadce0);
      border-radius: var(--card-border-radius, 8px);
    }
    .ps-header {
      display: flex;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 24px;
    }
    .ps-header-icon {
      width: 32px;
      height: 32px;
      font-size: 32px;
      color: var(--color-primary, #1a73e8);
    }
    .ps-title {
      margin: 0;
      font-size: 20px;
      font-weight: 500;
      color: var(--color-text-primary, #202124);
    }
    .ps-subtitle {
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--color-text-secondary, #5f6368);
    }
    .ps-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .ps-row {
      display: flex;
      gap: 12px;
      padding: 12px;
      background: var(--color-bg, #ffffff);
      border: var(--card-border, 0.8px solid #dadce0);
      border-radius: 4px;
    }
    .ps-row-icon mat-icon {
      width: 24px;
      height: 24px;
      font-size: 24px;
    }
    .ps-ready mat-icon { color: var(--color-success, #1e8e3e); }
    .ps-running mat-icon { color: var(--color-primary, #1a73e8); }
    .ps-stale mat-icon { color: var(--color-warning, #f9ab00); }
    .ps-blocked mat-icon { color: var(--color-error, #d93025); }
    .ps-not_configured mat-icon { color: var(--color-text-secondary, #5f6368); }
    .ps-row-body { flex: 1; }
    .ps-row-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .ps-row-name {
      font-weight: 500;
      font-size: 14px;
    }
    .ps-row-chip {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 12px;
      background: var(--color-bg-faint, #f1f3f4);
    }
    .ps-row-chip.ps-ready { background: #e6f4ea; color: #137333; }
    .ps-row-chip.ps-running { background: #e8f0fe; color: #1967d2; }
    .ps-row-chip.ps-stale { background: #fef7e0; color: #b06000; }
    .ps-row-chip.ps-blocked { background: #fce8e6; color: #c5221f; }
    .ps-row-reason {
      margin: 4px 0;
      font-size: 13px;
      color: var(--color-text-primary, #202124);
    }
    .ps-row-next {
      margin: 4px 0;
      font-size: 12px;
      color: var(--color-text-secondary, #5f6368);
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .ps-row-affects {
      margin: 4px 0 0;
      font-size: 11px;
      color: var(--color-text-secondary, #5f6368);
      font-style: italic;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .ps-affects-item { text-transform: capitalize; }
    .ps-loading {
      text-align: center;
      color: var(--color-text-secondary);
    }
    .ps-actions {
      margin-top: 24px;
      display: flex;
      justify-content: flex-end;
    }
    mat-progress-bar {
      margin-top: 8px;
    }
  `],
})
export class PreparingSuggestionsComponent {
  protected readiness = inject(SuggestionReadinessService);

  /** Hide / show the "Show me anyway" escape hatch. */
  @Input() allowOverride = true;

  iconFor(status: string): string {
    switch (status) {
      case 'ready': return 'check_circle';
      case 'running': return 'hourglass_bottom';
      case 'stale': return 'schedule';
      case 'blocked': return 'error';
      default: return 'help_outline';
    }
  }

  labelFor(status: string): string {
    switch (status) {
      case 'running': return 'In progress';
      case 'stale': return 'Stale';
      case 'blocked': return 'Blocked';
      case 'ready': return 'Ready';
      default: return status;
    }
  }

  /** Emitted when the user clicks "Show me anyway" — parent chooses
   *  whether to flip a session flag that relaxes the gate. */
  @Output() readonly override = new EventEmitter<void>();
}
