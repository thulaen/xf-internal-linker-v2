import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { TodayAction } from '../today-focus/today-focus.component';

/**
 * Phase D1 / Gap 54 — "Do these first" priority action queue.
 *
 * A ranked, numbered top-3 list of the most important things a
 * noob-operator can do right now. Distinct from `TodayFocusComponent`
 * (which shows ALL actions without ordinal framing) because noobs need
 * to be told what to click FIRST — "everything is important" is useless.
 *
 * Rules:
 *   - Exactly the top 3 actions (slice input).
 *   - Big round number badges (1, 2, 3).
 *   - Every row has a one-click launcher labeled "Do this".
 *   - If less than 3 actions exist, the ones we have render fine;
 *     nothing forces padding.
 *
 * Data source: reuses the existing `TodayAction[]` from
 * `/api/dashboard/today-actions/` — no new endpoint needed.
 */
@Component({
  selector: 'app-priority-action-queue',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
  ],
  template: `
    <mat-card class="paq-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="paq-avatar">playlist_play</mat-icon>
        <mat-card-title>Do these first</mat-card-title>
        <mat-card-subtitle>Your top {{ topActions.length }} for the next 30 minutes</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (topActions.length === 0) {
          <p class="paq-empty">
            <mat-icon class="paq-empty-icon">check_circle</mat-icon>
            Nothing urgent. Great time to review pending suggestions or
            explore the Link Graph.
          </p>
        } @else {
          <ol class="paq-list">
            @for (a of topActions; track a.title; let i = $index) {
              <li [class]="'paq-item severity-' + a.severity">
                <span class="paq-number" [attr.aria-hidden]="true">{{ i + 1 }}</span>
                <div class="paq-body">
                  <span class="paq-title">{{ a.title }}</span>
                  <span class="paq-reason">{{ a.reason }}</span>
                </div>
                <a
                  mat-flat-button
                  color="primary"
                  class="paq-cta"
                  [routerLink]="a.route"
                  [fragment]="a.deepLinkTarget || undefined"
                >
                  Do this
                  <mat-icon iconPositionEnd>arrow_forward</mat-icon>
                </a>
              </li>
            }
          </ol>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .paq-card { height: 100%; }
    .paq-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .paq-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .paq-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      border-radius: var(--card-border-radius, 8px);
      border: var(--card-border);
      background: var(--color-bg-white);
    }
    .paq-item.severity-error {
      border-color: var(--color-error);
      background: var(--color-error-50, rgba(217, 48, 37, 0.05));
    }
    .paq-item.severity-warning {
      border-color: var(--color-warning);
      background: var(--color-warning-light, rgba(249, 171, 0, 0.08));
    }
    .paq-number {
      flex-shrink: 0;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 600;
      font-size: 14px;
    }
    .paq-item.severity-error .paq-number { background: var(--color-error); }
    .paq-item.severity-warning .paq-number { background: var(--color-warning); }
    .paq-body {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .paq-title {
      font-weight: 500;
      font-size: 13px;
      color: var(--color-text-primary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .paq-reason {
      font-size: 12px;
      color: var(--color-text-secondary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .paq-cta {
      flex-shrink: 0;
    }
    .paq-empty {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .paq-empty-icon {
      color: var(--color-success, #1e8e3e);
    }
  `],
})
export class PriorityActionQueueComponent {
  @Input() set actions(next: readonly TodayAction[] | null | undefined) {
    // Top 3 only — that's the whole point of the card.
    this.topActions = (next ?? []).slice(0, 3);
  }

  /** The rendered top-3 slice. Never more than 3 items. */
  topActions: readonly TodayAction[] = [];
}
