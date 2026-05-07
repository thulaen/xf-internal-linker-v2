/**
 * Group M.1 — Admin Models page (``/admin/models``).
 *
 * Single source of operator control for every registered ML model
 * in the runtime registry: champion + candidate per task-type,
 * the placements showing where each model lives (primary or helper
 * PC), the seven action buttons (download / warm / pause / resume /
 * promote / rollback / drain), reclaimable-disk readout, and the
 * 10 most recent audit-log entries. Reuses the existing endpoints
 * shipped at ``/api/settings/runtime/models/``.
 *
 * Forward-thinking notes:
 *   * Material primitives only (mat-card / mat-tab-group / mat-chip /
 *     mat-button / mat-icon / mat-progress-bar / matTooltip).
 *   * Standalone + OnPush + signals — fits the rest of the codebase.
 *   * Confirm dialogs for the destructive trio (rollback / drain /
 *     placement delete) — follows the same pattern as the existing
 *     Settings pages and `Type-to-confirm` posture from the masterplan
 *     (Group Z FACTORY RESET button).
 */
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  RuntimeModel,
  RuntimeModelAction,
  RuntimeModelTaskType,
  RuntimeModelsService,
  RuntimeModelsSummary,
} from './runtime-models.service';

/** Plain-English label per task-type — surfaces on the tab heading. */
const TASK_TYPE_LABELS: Record<RuntimeModelTaskType, string> = {
  embedding: 'Embedding',
  classifier: 'Classifier',
  reranker: 'Reranker',
  kg: 'Knowledge Graph',
};

/** Match Material chip colour to model state — readable + a11y-friendly. */
function statusChipColor(status: string): 'primary' | 'accent' | 'warn' | undefined {
  switch (status) {
    case 'ready':
    case 'warming':
      return 'primary';
    case 'paused':
    case 'draining':
      return 'accent';
    case 'failed':
    case 'retired':
      return 'warn';
    default:
      return undefined;
  }
}

@Component({
  selector: 'app-admin-models',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDialogModule,
    MatDividerModule,
    MatIconModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTabsModule,
    MatTooltipModule,
  ],
  templateUrl: './admin-models.component.html',
  styleUrls: ['./admin-models.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AdminModelsComponent implements OnInit {
  private readonly svc = inject(RuntimeModelsService);
  private readonly snack = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  /** Tab order matches the operator's likely click frequency. */
  readonly taskTypes: ReadonlyArray<RuntimeModelTaskType> = [
    'embedding',
    'classifier',
    'reranker',
    'kg',
  ];

  readonly activeTaskType = signal<RuntimeModelTaskType>('embedding');
  readonly summary = signal<RuntimeModelsSummary | null>(null);
  readonly loading = signal<boolean>(true);
  readonly error = signal<string>('');
  readonly busyAction = signal<string>('');

  /** UI selectors (computed from the latest summary). */
  readonly placements = computed(() => this.summary()?.placements ?? []);
  readonly auditEntries = computed(() => this.summary()?.recent_audit_log ?? []);
  readonly hasModels = computed(() => {
    const s = this.summary();
    return !!(s?.active_model || s?.candidate_model || (s?.placements?.length ?? 0) > 0);
  });

  ngOnInit(): void {
    this.refresh(this.activeTaskType());
  }

  /** Plain-English heading for a tab. */
  taskLabel(t: RuntimeModelTaskType): string {
    return TASK_TYPE_LABELS[t] ?? t;
  }

  /** Material chip colour binding helper. */
  statusColor(status: string): 'primary' | 'accent' | 'warn' | undefined {
    return statusChipColor(status);
  }

  /** Convert raw bytes to a friendly string for the disk readout. */
  formatBytes(bytes: number | null | undefined): string {
    if (!bytes || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let n = bytes;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i += 1;
    }
    return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
  }

  onTabChange(idx: number): void {
    const next = this.taskTypes[idx];
    if (next && next !== this.activeTaskType()) {
      this.activeTaskType.set(next);
      this.refresh(next);
    }
  }

  refresh(taskType: RuntimeModelTaskType = this.activeTaskType()): void {
    this.loading.set(true);
    this.error.set('');
    this.svc
      .list(taskType)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => {
          this.summary.set(s);
          this.loading.set(false);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.error.set(this.extractErrorMessage(err, 'Could not load model registry.'));
        },
      });
  }

  /**
   * Run one of the seven supported actions against a model.
   * Destructive actions (``rollback``, ``drain``) get a confirm
   * step so the operator does not click them by accident. The
   * action endpoint returns a small status object; we refresh
   * the full summary afterward so the UI sees the new state.
   */
  runAction(model: RuntimeModel, action: RuntimeModelAction): void {
    if (this.busyAction()) return;

    const destructive = action === 'rollback' || action === 'drain';
    if (destructive && !this.confirmDestructive(model, action)) {
      return;
    }

    const key = `${model.id}:${action}`;
    this.busyAction.set(key);
    this.svc
      .action(model.id, action)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.snack.open(
            `Action "${action}" applied to ${model.model_name} (${resp.status}).`,
            undefined,
            { duration: 2500 },
          );
          // Refresh the full summary — the action endpoint only
          // returns the new status string, not the full envelope.
          this.svc
            .list(this.activeTaskType())
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: (s) => {
                this.summary.set(s);
                this.busyAction.set('');
              },
              error: () => {
                // Action succeeded but refresh failed — the snackbar
                // already showed success. Clear the busy flag so the
                // operator can manually click Refresh.
                this.busyAction.set('');
              },
            });
        },
        error: (err: unknown) => {
          this.busyAction.set('');
          this.snack.open(
            this.extractErrorMessage(err, `Action "${action}" failed.`),
            'Dismiss',
            { duration: 5000 },
          );
        },
      });
  }

  /** Whether the action button should show its inline spinner. */
  isBusy(modelId: number | undefined, action: RuntimeModelAction): boolean {
    if (modelId === undefined) return false;
    return this.busyAction() === `${modelId}:${action}`;
  }

  trackByPlacement(_: number, p: { id: number }): number {
    return p.id;
  }

  trackByAudit(_: number, e: { id: number }): number {
    return e.id;
  }

  /** Last-resort guard against accidental rollback / drain clicks. */
  private confirmDestructive(model: RuntimeModel, action: RuntimeModelAction): boolean {
    const verb = action === 'drain' ? 'drain' : 'roll back';
    return window.confirm(
      `Are you sure you want to ${verb} ${model.model_name}? ` +
        `This affects every running pipeline that uses this model.`,
    );
  }

  /** Pull a human-readable string from an HTTP error of any shape. */
  private extractErrorMessage(err: unknown, fallback: string): string {
    const e = err as { error?: { error?: string; detail?: string }; message?: string };
    return (
      e?.error?.error ?? e?.error?.detail ?? e?.message ?? fallback
    );
  }
}
