import { Component, inject, ChangeDetectionStrategy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { catchError, of } from 'rxjs';
import { Runbook } from '../runbook-library';

/**
 * Data accepted by RunbookDialogComponent. Historically just a Runbook; now
 * callers can pass { runbook, context } so runbook-specific backend args
 * (e.g. run_id for reset-quarantined-job) flow through without another dialog.
 */
export type RunbookDialogData =
  | Runbook
  | { runbook: Runbook; context?: Record<string, unknown> };

function isWrapped(
  data: RunbookDialogData,
): data is { runbook: Runbook; context?: Record<string, unknown> } {
  return !!data && typeof data === 'object' && 'runbook' in (data as object);
}

@Component({
  selector: 'app-runbook-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>{{ runbook.title }}</h2>
    <mat-dialog-content>
      <section class="runbook-section">
        <h4 class="section-label">Problem</h4>
        <p class="section-text">{{ runbook.plainEnglishProblem }}</p>
      </section>

      <section class="runbook-section">
        <h4 class="section-label">Plan</h4>
        <ol class="step-list">
          @for (step of runbook.steps; track step.description) {
            <li [class.destructive]="step.isDestructive">
              {{ step.description }}
              @if (step.isDestructive) {
                <mat-chip class="destructive-chip" disableRipple>Requires confirmation</mat-chip>
              }
            </li>
          }
        </ol>
      </section>

      <div class="runbook-meta">
        <div class="meta-item">
          <span class="meta-label">Resource level</span>
          <mat-chip [class]="'resource-' + runbook.resourceLevel" disableRipple>
            {{ runbook.resourceLevel }}
          </mat-chip>
        </div>
        <div class="meta-item">
          <span class="meta-label">What it pauses</span>
          <span class="meta-value">{{ runbook.whatItWillPause }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Stop condition</span>
          <span class="meta-value">{{ runbook.stopCondition }}</span>
        </div>
      </div>
    </mat-dialog-content>
    @if (resultMessage()) {
      <div class="runbook-result" [class.runbook-result-ok]="resultOk()">
        <mat-icon>{{ resultOk() ? 'check_circle' : 'error' }}</mat-icon>
        <span>{{ resultMessage() }}</span>
      </div>
    }
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close [disabled]="running()">Cancel</button>
      <button mat-flat-button color="primary"
              [disabled]="running()"
              (click)="runFix()">
        @if (running()) {
          <mat-spinner diameter="18" class="btn-spinner"></mat-spinner>
        } @else {
          <mat-icon>play_arrow</mat-icon>
        }
        Run this fix
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .runbook-section { margin-bottom: var(--space-lg); }
    .section-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--color-text-muted);
      margin: 0 0 var(--space-xs);
    }
    .section-text {
      font-size: 13px;
      color: var(--color-text-primary);
      margin: 0;
    }
    .step-list {
      padding-left: 20px;
      margin: 0;
    }
    .step-list li {
      font-size: 13px;
      color: var(--color-text-primary);
      margin-bottom: var(--space-sm);
      line-height: 1.5;
    }
    .step-list li.destructive { color: var(--color-error-dark); }
    .destructive-chip {
      --mdc-chip-elevated-container-color: var(--color-error-50);
      --mdc-chip-label-text-color: var(--color-error-dark);
      font-size: 10px;
      height: 20px;
      margin-left: var(--space-sm);
    }
    .runbook-meta {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      padding: var(--space-md);
      background: var(--color-bg-faint);
      border-radius: var(--radius-md);
    }
    .meta-item { display: flex; align-items: center; gap: var(--space-sm); }
    .meta-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--color-text-muted);
      min-width: 100px;
    }
    .meta-value {
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .resource-low {
      --mdc-chip-elevated-container-color: var(--color-success-light);
      --mdc-chip-label-text-color: var(--color-success-dark);
    }
    .resource-medium {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .resource-high {
      --mdc-chip-elevated-container-color: var(--color-error-50);
      --mdc-chip-label-text-color: var(--color-error-dark);
    }
    .btn-spinner {
      margin-right: var(--space-xs);
      display: inline-block;
      vertical-align: middle;
    }
    .runbook-result {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      margin: var(--space-md) var(--space-lg) 0;
      border-radius: var(--radius-sm);
      font-size: 13px;
      background: var(--color-error-50);
      color: var(--color-error-dark);
    }
    .runbook-result.runbook-result-ok {
      background: var(--color-success-light);
      color: var(--color-success-dark);
    }
  `],
})
export class RunbookDialogComponent {
  private readonly _data = inject<RunbookDialogData>(MAT_DIALOG_DATA);

  readonly runbook: Runbook = isWrapped(this._data) ? this._data.runbook : this._data;
  private readonly context: Record<string, unknown> = isWrapped(this._data)
    ? (this._data.context ?? {})
    : {};

  private http = inject(HttpClient);
  private dialogRef = inject(MatDialogRef<RunbookDialogComponent>);
  private snack = inject(MatSnackBar);

  running = signal(false);
  resultMessage = signal<string>('');
  resultOk = signal(false);

  /**
   * Call the matching backend runbook endpoint (plan item 17). Destructive
   * runbooks require ``confirmed=true`` in the body — we send it here because
   * the user has already seen the full plan + stop condition in this dialog
   * and chosen to proceed. The backend is idempotent so re-running is safe.
   */
  runFix(): void {
    if (this.running()) return;
    this.running.set(true);
    this.resultMessage.set('');

    const url = `/api/runbooks/${this.runbook.id}/execute/`;
    const body = { confirmed: true, ...this.context };
    this.http
      .post<{ ok: boolean; action: string; detail?: string }>(url, body)
      .pipe(
        catchError((err) => {
          const detail = err?.error?.detail || 'Unknown error';
          return of({ ok: false, action: 'error', detail } as {
            ok: boolean;
            action: string;
            detail?: string;
          });
        }),
      )
      .subscribe((res) => {
        this.running.set(false);
        this.resultOk.set(!!res.ok);
        this.resultMessage.set(this.describe(res));
        if (res.ok) {
          this.snack.open(this.describe(res), 'OK', { duration: 4000 });
          // Close after a short delay so the user can read the success state.
          setTimeout(() => this.dialogRef.close(true), 1200);
        }
      });
  }

  private describe(res: { ok: boolean; action: string; detail?: string }): string {
    if (!res.ok) return res.detail || 'Runbook failed — check backend logs.';
    switch (res.action) {
      case 'already_done':
        return 'Nothing to do — the system is already in the target state.';
      case 'preview_only':
        return res.detail || 'Preview only. Full enforcement ships in a later phase.';
      case 'rechecked':
        return 'Health services rechecked. Refresh the Health page to see the latest status.';
      case 'cleaned':
        return res.detail || 'Stale alerts cleaned up.';
      case 'reset':
        return 'Quarantine cleared. The job can be retried.';
      case 'unstuck':
        return res.detail || 'Stuck runs marked failed. Retry from the Jobs page.';
      default:
        return res.detail || 'Runbook completed.';
    }
  }
}
