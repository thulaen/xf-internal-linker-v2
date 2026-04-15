import { ChangeDetectionStrategy, Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Plain-English summary of the scheduling policy (plan item 11, part 2).
 *
 * This card is reference material, not live data: it explains the task
 * weight classes, the evening maintenance window, and the stagger rule
 * exactly as documented in `docs/PERFORMANCE.md` §§4-5. It renders next to
 * the live `<app-system-metrics>` block so the user can read current load
 * and understand *why* the scheduler behaves the way it does.
 *
 * Why this isn't "live data":
 *   docs/PERFORMANCE.md is the source of truth for the class membership.
 *   Hard-coding the mapping in frontend code would create drift. Instead we
 *   surface the groupings and any real-time "which task is where" detail
 *   belongs in the job rows themselves (future work with backend support).
 */
@Component({
  selector: 'app-scheduling-policy-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatCardModule,
    MatChipsModule,
    MatExpansionModule,
    MatIconModule,
    MatTooltipModule,
  ],
  template: `
    <mat-card class="policy-card" id="scheduling-policy-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="policy-avatar">rule</mat-icon>
        <mat-card-title>Scheduling policy</mat-card-title>
        <mat-card-subtitle>
          Why jobs run when they run \u2014 from
          <a href="https://example.invalid" (click)="$event.preventDefault()" matTooltip="See docs/PERFORMANCE.md in the repo">docs/PERFORMANCE.md</a>
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <ul class="policy-rules">
          <li>
            <mat-chip class="policy-chip weight-heavy" disableRipple>Heavy</mat-chip>
            <span class="rule-text">
              <strong>Max one at a time.</strong> Heavy tasks (peak memory &gt; 1 GB) run
              one-by-one on the <code>pipeline</code> queue. Heavy jobs wait while another
              heavy job is running \u2014 this prevents out-of-memory kills.
            </span>
          </li>
          <li>
            <mat-chip class="policy-chip weight-medium" disableRipple>Medium</mat-chip>
            <span class="rule-text">
              <strong>Max one at a time.</strong> Medium tasks (200 MB \u2013 1 GB peak)
              share the same FIFO lock as Heavy but release faster.
            </span>
          </li>
          <li>
            <mat-chip class="policy-chip weight-light" disableRipple>Light</mat-chip>
            <span class="rule-text">
              <strong>Unlimited parallel.</strong> Light tasks (under 200 MB) run on the
              <code>default</code> queue with no lock. Heartbeats, cleanups, and small
              tallies fall here.
            </span>
          </li>
          <li class="policy-divider"></li>
          <li>
            <mat-icon class="rule-icon">bedtime</mat-icon>
            <span class="rule-text">
              <strong>Evening window 21:00 \u2013 22:30 UTC</strong> is reserved for Heavy
              and Medium jobs so daytime Chrome work isn't starved of RAM.
            </span>
          </li>
          <li>
            <mat-icon class="rule-icon">hourglass_bottom</mat-icon>
            <span class="rule-text">
              <strong>30-second stagger</strong> between consecutive Heavy tasks on worker
              startup keeps the catch-up system from spiking memory at once.
            </span>
          </li>
          <li>
            <mat-icon class="rule-icon">thermostat</mat-icon>
            <span class="rule-text">
              <strong>76 \u00B0C GPU ceiling.</strong> Any GPU task auto-pauses at 76 \u00B0C and
              only resumes below 68 \u00B0C. See Performance Mode for the current cap.
            </span>
          </li>
        </ul>

        <mat-accordion class="examples-accordion">
          <mat-expansion-panel class="examples-panel">
            <mat-expansion-panel-header>
              <mat-panel-title>
                <mat-icon class="expand-icon">list</mat-icon>
                Example tasks in each class
              </mat-panel-title>
            </mat-expansion-panel-header>
            <dl class="class-list">
              <dt><mat-chip class="policy-chip weight-heavy" disableRipple>Heavy</mat-chip></dt>
              <dd>nightly-xenforo-sync, monthly-xenforo-full-sync, monthly-wordpress-full-sync</dd>

              <dt><mat-chip class="policy-chip weight-medium" disableRipple>Medium</mat-chip></dt>
              <dd>monthly-cs-weight-tune, weekly-session-cooccurrence</dd>

              <dt><mat-chip class="policy-chip weight-light" disableRipple>Light</mat-chip></dt>
              <dd>
                nightly-data-retention, cleanup-stuck-sync-jobs, nightly-benchmarks,
                pulse-heartbeat, watchdog-check, refresh-faiss-index, auto-prune, plus
                five smaller housekeeping jobs.
              </dd>
            </dl>
          </mat-expansion-panel>
        </mat-accordion>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .policy-card { padding: var(--spacing-card); }
    .policy-avatar {
      background: var(--color-blue-50);
      color: var(--color-primary);
    }
    mat-card-subtitle a {
      color: var(--color-primary);
      text-decoration: none;
      font-family: inherit;
    }
    mat-card-subtitle a:hover { text-decoration: underline; }

    .policy-rules {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }
    .policy-rules > li {
      display: flex;
      align-items: flex-start;
      gap: var(--space-md);
      font-size: 13px;
      line-height: 1.5;
      color: var(--color-text-secondary);
    }
    .policy-rules > li.policy-divider {
      border-top: var(--card-border);
      margin: var(--space-sm) 0 0 0;
      padding-top: var(--space-sm);
      display: block;
      height: 0;
    }
    .rule-text { flex: 1; min-width: 0; }
    .rule-text strong { color: var(--color-text-primary); font-weight: 600; }
    .rule-text code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      padding: 1px 4px;
      background: var(--color-bg-faint);
      border-radius: var(--radius-sm);
      color: var(--color-text-primary);
    }
    .rule-icon {
      color: var(--color-text-muted);
      font-size: 18px;
      width: 18px;
      height: 18px;
      flex-shrink: 0;
      margin-top: 2px;
    }

    .policy-chip {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      min-width: 68px;
      justify-content: center;
      flex-shrink: 0;
    }
    .weight-heavy {
      --mdc-chip-elevated-container-color: var(--color-error-50);
      --mdc-chip-label-text-color: var(--color-error-dark);
    }
    .weight-medium {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .weight-light {
      --mdc-chip-elevated-container-color: var(--color-success-light);
      --mdc-chip-label-text-color: var(--color-success-dark);
    }

    .examples-accordion {
      margin-top: var(--space-md);
      box-shadow: none;
    }
    .examples-panel {
      box-shadow: none !important;
      border: var(--card-border);
      border-radius: var(--radius-md) !important;
    }
    .expand-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      margin-right: var(--space-xs);
      color: var(--color-primary);
    }

    .class-list {
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: auto 1fr;
      gap: var(--space-sm) var(--space-md);
      align-items: center;
      font-size: 12px;
    }
    .class-list dt {
      margin: 0;
    }
    .class-list dd {
      margin: 0;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
  `],
})
export class SchedulingPolicyCardComponent {}
