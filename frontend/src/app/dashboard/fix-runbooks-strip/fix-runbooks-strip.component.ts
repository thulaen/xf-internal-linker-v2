import { ChangeDetectionStrategy, Component, Input, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Runbook, RUNBOOK_LIBRARY } from '../../shared/runbooks/runbook-library';
import { RunbookDialogComponent } from '../../shared/runbooks/runbook-dialog/runbook-dialog.component';

/**
 * Dashboard "Fix Runbooks" strip (plan item 7).
 *
 * Shown only when there is at least one open health issue or quarantine item.
 * Hidden otherwise — no quiet clutter on a healthy system.
 *
 * Clicking a button opens the existing `RunbookDialogComponent` so there is no
 * duplicate repair UI.
 */
@Component({
  selector: 'app-fix-runbooks-strip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatTooltipModule,
  ],
  template: `
    @if (visible()) {
      <section class="fix-strip" id="fix-runbooks-strip" role="region" aria-label="Quick fix runbooks">
        <header class="fix-strip-header">
          <mat-icon class="fix-strip-icon">build_circle</mat-icon>
          <div class="fix-strip-text">
            <span class="fix-strip-title">Quick fixes available</span>
            <span class="fix-strip-subtitle">{{ subtitle() }}</span>
          </div>
        </header>
        <div class="fix-strip-actions">
          @for (rb of runbooks(); track rb.id) {
            <button
              mat-stroked-button
              class="fix-strip-btn"
              (click)="open(rb)"
              [matTooltip]="rb.plainEnglishProblem"
            >
              <mat-icon>{{ iconFor(rb.id) }}</mat-icon>
              <span class="fix-strip-btn-label">{{ rb.title }}</span>
            </button>
          }
        </div>
      </section>
    }
  `,
  styles: [`
    .fix-strip {
      display: flex;
      flex-direction: column;
      gap: var(--space-md);
      padding: var(--spacing-card);
      margin-bottom: var(--space-lg);
      background: var(--color-warning-light);
      border: 1px solid var(--color-warning);
      border-radius: var(--card-border-radius, 8px);
    }
    .fix-strip-header {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .fix-strip-icon {
      color: var(--color-warning-dark);
      font-size: 24px;
      width: 24px;
      height: 24px;
      flex-shrink: 0;
    }
    .fix-strip-text {
      display: flex;
      flex-direction: column;
      line-height: 1.3;
      min-width: 0;
    }
    .fix-strip-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--color-warning-dark);
    }
    .fix-strip-subtitle {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .fix-strip-actions {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    .fix-strip-btn {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      white-space: nowrap;
    }
    .fix-strip-btn mat-icon {
      color: var(--color-warning-dark);
    }
    .fix-strip-btn-label {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 240px;
    }
  `],
})
export class FixRunbooksStripComponent {
  private dialog = inject(MatDialog);

  /** Accepts the DashboardData.system_health.status string verbatim. */
  @Input() healthStatus: string | null | undefined = 'healthy';

  /** Count of quarantined items. 0 means no quarantine pressure. */
  @Input() openQuarantineCount = 0;

  private readonly status = signal<string>('healthy');
  private readonly quarantine = signal<number>(0);

  // Keep the signals in sync with @Input() changes.
  ngOnChanges(): void {
    this.status.set(this.healthStatus ?? 'healthy');
    this.quarantine.set(this.openQuarantineCount);
  }

  readonly visible = computed<boolean>(() => {
    return this.status() !== 'healthy' || this.quarantine() > 0;
  });

  readonly subtitle = computed<string>(() => {
    const parts: string[] = [];
    const s = this.status();
    if (s === 'error' || s === 'down') parts.push('One or more services are down');
    else if (s === 'warning' || s === 'stale') parts.push('One or more services are degraded');
    if (this.quarantine() > 0) {
      const n = this.quarantine();
      parts.push(`${n} job${n === 1 ? '' : 's'} quarantined`);
    }
    return parts.length > 0 ? parts.join(' \u2022 ') : 'Open issues detected.';
  });

  readonly runbooks = computed<Runbook[]>(() => {
    const ids: string[] = [];
    if (this.status() !== 'healthy') {
      ids.push('recheck-health-services', 'restart-stuck-pipeline');
    }
    if (this.quarantine() > 0) {
      ids.push('reset-quarantined-job');
    }
    // Preserve library order, dedupe.
    const seen = new Set(ids);
    return RUNBOOK_LIBRARY.filter((rb) => seen.has(rb.id));
  });

  iconFor(id: string): string {
    const map: Record<string, string> = {
      'restart-stuck-pipeline': 'replay_circle_filled',
      'clear-stale-alerts': 'clear_all',
      'recheck-health-services': 'refresh',
      'prune-docker-artifacts': 'delete_sweep',
      'reset-quarantined-job': 'healing',
      'retrigger-embedding': 'psychology',
    };
    return map[id] ?? 'build';
  }

  open(rb: Runbook): void {
    this.dialog.open(RunbookDialogComponent, {
      data: rb,
      width: '520px',
      maxWidth: '92vw',
      autoFocus: 'first-tabbable',
      restoreFocus: true,
    });
  }
}
