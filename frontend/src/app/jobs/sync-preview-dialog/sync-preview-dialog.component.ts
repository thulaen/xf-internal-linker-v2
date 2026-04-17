import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { catchError, of } from 'rxjs';

export interface SyncPreviewDialogData {
  source: 'api' | 'wp';
  mode: string;
}

interface PreviewResult {
  ok: boolean;
  source: string;
  mode: string;
  items_seen: number;
  items_would_import: number;
  items_would_skip: number;
  items_would_update: number;
  truncated_by_cap: boolean;
  elapsed_seconds: number;
  artifact_path: string;
  notes: string[];
}

/**
 * Dry-run sync preview dialog (plan item 25).
 *
 * Calls POST /api/sync/preview/ on open, shows the results when they land,
 * and offers the user a clear "Cancel" or "Run for real" path. Never runs
 * the real sync itself — the parent component owns that action.
 */
@Component({
  selector: 'app-sync-preview-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatChipsModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="preview-title-icon">visibility</mat-icon>
      Preview: {{ sourceLabel() }} sync ({{ data.mode }})
    </h2>
    <mat-dialog-content>
      <p class="preview-intro">
        The sampler ran against the last-seen metadata — no full bodies,
        no embeddings, no writes. Capped at 3 minutes.
      </p>

      @if (loading()) {
        <div class="preview-loading">
          <mat-spinner diameter="32"></mat-spinner>
          <span>Running preview…</span>
        </div>
      } @else if (error()) {
        <div class="preview-error">
          <mat-icon>error</mat-icon>
          <span>{{ error() }}</span>
        </div>
      } @else if (result(); as r) {
        <div class="preview-stats">
          <div class="preview-stat">
            <span class="stat-value">{{ r.items_seen }}</span>
            <span class="stat-label">Items sampled</span>
          </div>
          <div class="preview-stat preview-stat-import">
            <span class="stat-value">{{ r.items_would_import }}</span>
            <span class="stat-label">Would import</span>
          </div>
          <div class="preview-stat preview-stat-update">
            <span class="stat-value">{{ r.items_would_update }}</span>
            <span class="stat-label">Would update</span>
          </div>
          <div class="preview-stat preview-stat-skip">
            <span class="stat-value">{{ r.items_would_skip }}</span>
            <span class="stat-label">Would skip</span>
          </div>
        </div>

        <div class="preview-meta">
          <mat-chip disableRipple>
            <mat-icon>schedule</mat-icon>
            {{ r.elapsed_seconds }}s elapsed
          </mat-chip>
          @if (r.truncated_by_cap) {
            <mat-chip disableRipple class="chip-warn">
              <mat-icon>timer_off</mat-icon>
              Hit 3-min cap
            </mat-chip>
          }
        </div>

        @if (r.notes && r.notes.length > 0) {
          <ul class="preview-notes">
            @for (note of r.notes; track note) {
              <li>{{ note }}</li>
            }
          </ul>
        }
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="'cancel'" [disabled]="loading()">Cancel</button>
      <button mat-flat-button
              color="primary"
              [disabled]="loading() || !result()?.ok"
              [mat-dialog-close]="'run'">
        <mat-icon>play_arrow</mat-icon>
        Run for real
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .preview-title-icon {
      vertical-align: middle;
      margin-right: var(--space-xs);
      color: var(--color-primary);
    }
    .preview-intro {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 var(--space-md);
      line-height: 1.5;
    }
    .preview-loading {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-md);
      padding: var(--space-xl) 0;
      color: var(--color-text-secondary);
    }
    .preview-error {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-md);
      background: var(--color-error-50);
      color: var(--color-error-dark);
      border-radius: var(--radius-sm);
    }
    .preview-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: var(--space-sm);
      margin: var(--space-md) 0;
    }
    .preview-stat {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
      padding: var(--space-md);
      border: var(--card-border);
      border-radius: var(--radius-md);
      background: var(--color-bg-faint);
    }
    .stat-value {
      font-size: 24px;
      font-weight: 600;
      color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
    }
    .stat-label {
      font-size: 11px;
      color: var(--color-text-muted);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .preview-stat-import .stat-value { color: var(--color-primary); }
    .preview-stat-update .stat-value { color: var(--color-warning-dark); }
    .preview-stat-skip .stat-value { color: var(--color-success-dark); }

    .preview-meta {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      margin: 0 0 var(--space-md);
    }
    .chip-warn {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .preview-notes {
      margin: 0;
      padding-left: 20px;
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.6;
    }
  `],
})
export class SyncPreviewDialogComponent {
  data = inject<SyncPreviewDialogData>(MAT_DIALOG_DATA);
  private http = inject(HttpClient);
  private dialogRef = inject(MatDialogRef<SyncPreviewDialogComponent>);
  // Phase E2 / Gap 41 — cancel in-flight preview if dialog closes first.
  private destroyRef = inject(DestroyRef);

  loading = signal(true);
  result = signal<PreviewResult | null>(null);
  error = signal<string>('');

  constructor() {
    this.http
      .post<PreviewResult>('/api/sync/preview/', {
        source: this.data.source,
        mode: this.data.mode,
        sample_size: 10,
      })
      .pipe(
        catchError((err) => {
          // Surface the backend's plain-English detail when present so the
          // user sees something more useful than "Preview failed.".
          const detail = err?.error?.detail || err?.message || 'Preview failed.';
          this.error.set(detail);
          return of<PreviewResult | null>(null);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        if (res) {
          this.result.set(res);
        } else if (!this.error()) {
          this.error.set('Preview failed — see backend logs for details.');
        }
        this.loading.set(false);
      });
  }

  sourceLabel(): string {
    return this.data.source === 'api' ? 'XenForo' : 'WordPress';
  }
}
