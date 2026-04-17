import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, of } from 'rxjs';

import { FeatureFlagsService } from '../../core/services/feature-flags.service';

/**
 * Phase OB / Gap 131 — In-app Feature-flag admin.
 *
 * Lists every flag the backend knows about with its enabled state +
 * rollout percent + variant summary. Operators with staff access can
 * toggle a flag from the UI; anything else (variant editing, rollout
 * percent, creating new flags) is deferred to Django admin which the
 * backend model already registers.
 *
 * The frontend flag service refetches after every toggle so
 * downstream components pick up the new state within a second.
 *
 * Degradation: if the `/api/feature-flags/admin/` endpoint doesn't
 * exist yet, the component shows a "not configured" message with a
 * link to Django admin.
 */

interface FlagRow {
  key: string;
  description: string;
  enabled: boolean;
  rollout_percent: number;
  variants: { name: string; weight: number }[];
}

@Component({
  selector: 'app-feature-flags-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule,
    MatSlideToggleModule,
    MatIconModule,
  ],
  template: `
    <mat-card class="ffp-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="ffp-avatar">flag_circle</mat-icon>
        <mat-card-title>Feature flags</mat-card-title>
        <mat-card-subtitle>{{ flags().length }} flags configured</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (unavailable()) {
          <p class="ffp-hint">
            The admin API isn't configured on this server yet. Use
            <a href="/admin/core/featureflag/" target="_blank" rel="noopener">
              Django admin
            </a>
            to manage flags.
          </p>
        } @else if (flags().length === 0) {
          <p class="ffp-hint">No flags yet. Create one in Django admin.</p>
        } @else {
          <table class="ffp-table" aria-label="Feature flags">
            <thead>
              <tr>
                <th scope="col">Flag</th>
                <th scope="col">Rollout</th>
                <th scope="col">Variants</th>
                <th scope="col">Enabled</th>
              </tr>
            </thead>
            <tbody>
              @for (row of flags(); track row.key) {
                <tr>
                  <th scope="row" class="ffp-key">
                    <strong>{{ row.key }}</strong>
                    @if (row.description) {
                      <span class="ffp-desc">{{ row.description }}</span>
                    }
                  </th>
                  <td>{{ row.rollout_percent }}%</td>
                  <td>
                    @if (row.variants.length === 0) {
                      <span class="ffp-dim">—</span>
                    } @else {
                      <span class="ffp-variants">
                        @for (v of row.variants; track v.name) {
                          <span class="ffp-variant">
                            {{ v.name }}:{{ v.weight }}
                          </span>
                        }
                      </span>
                    }
                  </td>
                  <td>
                    <mat-slide-toggle
                      color="primary"
                      [checked]="row.enabled"
                      [disabled]="busyKey() === row.key"
                      (change)="onToggle(row, $event.checked)"
                    />
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .ffp-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .ffp-hint {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .ffp-table {
      width: 100%;
      border-collapse: collapse;
    }
    .ffp-table th, .ffp-table td {
      padding: 6px 8px;
      text-align: left;
      border-bottom: 1px solid var(--color-border-faint);
      font-size: 13px;
      vertical-align: top;
    }
    .ffp-table thead th {
      font-size: 11px;
      font-weight: 500;
      color: var(--color-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .ffp-key {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .ffp-desc {
      font-size: 11px;
      color: var(--color-text-secondary);
      font-weight: 400;
    }
    .ffp-variants {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    .ffp-variant {
      padding: 2px 6px;
      background: var(--color-bg-faint);
      border-radius: 10px;
      font-size: 11px;
    }
    .ffp-dim { color: var(--color-text-secondary); }
  `],
})
export class FeatureFlagsPanelComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly service = inject(FeatureFlagsService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly flags = signal<readonly FlagRow[]>([]);
  readonly unavailable = signal<boolean>(false);
  readonly busyKey = signal<string>('');

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.http
      .get<FlagRow[]>('/api/feature-flags/admin/')
      .pipe(
        catchError((err) => {
          this.unavailable.set(err?.status === 404);
          return of<FlagRow[]>([]);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((rows) => {
        this.flags.set(rows);
      });
  }

  onToggle(row: FlagRow, enabled: boolean): void {
    if (this.busyKey()) return;
    this.busyKey.set(row.key);
    this.http
      .patch<FlagRow>(`/api/feature-flags/admin/${encodeURIComponent(row.key)}/`, {
        enabled,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.busyKey.set('');
          this.flags.set(
            this.flags().map((f) => (f.key === updated.key ? updated : f)),
          );
          this.service.refresh();
          this.snack.open(
            `Flag "${row.key}" ${enabled ? 'enabled' : 'disabled'}.`,
            'OK',
            { duration: 3000 },
          );
        },
        error: (err) => {
          this.busyKey.set('');
          this.snack.open(
            err?.status === 404
              ? 'Admin API not configured — use Django admin.'
              : 'Could not update flag — try again.',
            'Dismiss',
            { duration: 5000 },
          );
        },
      });
  }
}
