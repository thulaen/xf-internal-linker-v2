import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, of } from 'rxjs';

interface AllowedTarget {
  id: string;
  label: string;
  detail: string;
  approx_reclaim_mb: number;
}

interface SafePruneStatus {
  allowed_targets: AllowedTarget[];
  deny_list: string[];
  idle: boolean;
  notes: string[];
}

/**
 * Safe-prune card on the /health page (plan item 26).
 *
 * Calls GET /api/prune/safe/ on init to learn which targets are allowed
 * and whether the system is idle. Each target renders as a row with a
 * "Preview" button (dry-run POST) and, after preview, a "Prune" commit
 * button that is only enabled when idle.
 *
 * Never fabricates targets — the backend is the source of truth. If
 * anything tries to prune a DB volume / media / embeddings, the backend
 * returns 403 (deny-list match) and we surface the error verbatim.
 */
@Component({
  selector: 'app-safe-prune-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  template: `
    <mat-card class="prune-card" id="safe-prune" data-ga4-panel>
      <mat-card-header>
        <mat-icon mat-card-avatar class="prune-avatar">delete_sweep</mat-icon>
        <mat-card-title>Safe prune</mat-card-title>
        <mat-card-subtitle>
          Reclaim disposable disk without touching data
        </mat-card-subtitle>
      </mat-card-header>

      <mat-card-content>
        @if (loading()) {
          <div class="prune-loading">
            <mat-spinner diameter="24"></mat-spinner>
          </div>
        } @else if (status(); as s) {
          <div class="idle-banner" [class.idle-banner-ok]="s.idle">
            <mat-icon>{{ s.idle ? 'check_circle' : 'warning' }}</mat-icon>
            <span>
              @if (s.idle) {
                System is idle — prune is allowed.
              } @else {
                A sync or pipeline is running. Commit prune is blocked until the system is idle.
              }
            </span>
          </div>

          <div class="targets">
            @for (target of s.allowed_targets; track target.id) {
              <div class="target-row">
                <div class="target-info">
                  <span class="target-label">{{ target.label }}</span>
                  <span class="target-detail">{{ target.detail }}</span>
                  <span class="target-est">~{{ target.approx_reclaim_mb }} MB reclaimable</span>
                </div>
                <div class="target-actions">
                  <button mat-stroked-button
                          [disabled]="busyTarget() === target.id"
                          (click)="runPreview(target.id)"
                          matTooltip="Dry-run preview — no data is touched"
                          matTooltipPosition="left">
                    <mat-icon>preview</mat-icon>
                    Preview
                  </button>
                  <button mat-flat-button color="primary"
                          [disabled]="!s.idle || busyTarget() === target.id"
                          (click)="commit(target.id)"
                          matTooltip="{{ s.idle ? 'Commit the prune' : 'Blocked: system is not idle' }}"
                          matTooltipPosition="left">
                    @if (busyTarget() === target.id) {
                      <mat-spinner diameter="18"></mat-spinner>
                    } @else {
                      <mat-icon>delete_sweep</mat-icon>
                    }
                    Prune
                  </button>
                </div>
              </div>
            }
          </div>

          <details class="deny-disclosure">
            <summary>Never touched — hardcoded deny list</summary>
            <p>
              These substrings are rejected by the backend even if a UI bug
              tried to request them: {{ s.deny_list.join(', ') }}.
            </p>
          </details>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .prune-card {
      padding: var(--spacing-card);
      margin: var(--space-md) 0;
    }
    .prune-avatar {
      background: var(--color-warning-light);
      color: var(--color-warning-dark);
    }
    .prune-loading {
      display: flex;
      justify-content: center;
      padding: var(--space-lg);
    }
    .idle-banner {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-sm);
      margin-bottom: var(--space-md);
      background: var(--color-warning-light);
      color: var(--color-warning-dark);
      font-size: 13px;
    }
    .idle-banner-ok {
      background: var(--color-success-light);
      color: var(--color-success-dark);
    }
    .targets {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }
    .target-row {
      display: flex;
      align-items: flex-start;
      gap: var(--space-md);
      padding: var(--space-md);
      border: var(--card-border);
      border-radius: var(--radius-md);
    }
    .target-info {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .target-label {
      font-weight: 600;
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .target-detail {
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
    .target-est {
      font-size: 11px;
      color: var(--color-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .target-actions {
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
      min-width: 120px;
    }
    .deny-disclosure {
      margin-top: var(--space-md);
      padding: var(--space-sm) var(--space-md);
      background: var(--color-bg-faint);
      border-radius: var(--radius-sm);
      font-size: 12px;
    }
    .deny-disclosure summary {
      cursor: pointer;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .deny-disclosure p {
      margin: var(--space-xs) 0 0;
      color: var(--color-text-secondary);
      font-family: var(--font-mono);
      font-size: 11px;
      word-break: break-all;
    }
  `],
})
export class SafePruneCardComponent implements OnInit {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);

  loading = signal(true);
  status = signal<SafePruneStatus | null>(null);
  busyTarget = signal<string>('');

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.http
      .get<SafePruneStatus>('/api/prune/safe/')
      .pipe(catchError(() => of<SafePruneStatus | null>(null)), takeUntilDestroyed(this.destroyRef))
      .subscribe((res) => {
        this.status.set(res);
        this.loading.set(false);
      });
  }

  runPreview(targetId: string): void {
    this.busyTarget.set(targetId);

    type PreviewResponse = { ok: boolean; estimated_reclaim_mb?: number; detail?: string };

    this.http
      .post<PreviewResponse>('/api/prune/safe/', { target: targetId })
      .pipe(
        catchError((err) => {
          const detail = err?.error?.detail || 'Preview failed.';
          return of<PreviewResponse>({ ok: false, detail });
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        this.busyTarget.set('');
        if (res.ok) {
          this.snack.open(
            `Preview: ~${res.estimated_reclaim_mb ?? '?'} MB would be reclaimed. Click Prune to commit.`,
            'OK',
            { duration: 6000 },
          );
        } else {
          this.snack.open(res.detail || 'Preview failed', 'OK', { duration: 5000 });
        }
      });
  }

  commit(targetId: string): void {
    if (!confirm(`Prune "${targetId}"? This is reversible on the next build.`)) return;
    this.busyTarget.set(targetId);

    type CommitResponse = { ok: boolean; reclaimed_mb?: number; detail?: string };

    this.http
      .post<CommitResponse>('/api/prune/safe/', { target: targetId, confirmed: true })
      .pipe(
        catchError((err) => {
          const detail = err?.error?.detail || 'Prune failed.';
          return of<CommitResponse>({ ok: false, detail });
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        this.busyTarget.set('');
        if (res.ok) {
          this.snack.open(
            `Pruned ${targetId}. Reclaimed ~${res.reclaimed_mb ?? '?'} MB.`,
            'OK',
            { duration: 6000 },
          );
          this.reload();
        } else {
          this.snack.open(res.detail || 'Prune failed', 'OK', { duration: 5000 });
        }
      });
  }
}
