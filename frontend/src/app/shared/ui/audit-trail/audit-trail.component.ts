import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Input,
  OnChanges,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { catchError, of } from 'rxjs';

import { TimeAgoPipe } from '../../pipes/time-ago.pipe';
import { IntlDateTimePipe } from '../../pipes/intl.pipes';

/**
 * Phase DC / Gap 118 — Per-entity audit trail viewer.
 *
 * Lists the existing `AuditEntry` rows for a given entity (target_type
 * + target_id). The backend `/api/audit-entries/` endpoint already
 * supports filtering — this component just wraps the call in an
 * opinionated UI that's consistent everywhere.
 *
 * Usage:
 *
 *   <app-audit-trail
 *     targetType="suggestion"
 *     [targetId]="suggestion.id" />
 *
 * Shows a chronological list of actions with actor (if logged),
 * action verb, and a relative + absolute timestamp. Empty state
 * when the entity has no history yet.
 */

interface AuditEntry {
  id: number;
  action: string;
  target_type: string;
  target_id: string;
  detail: unknown;
  ip_address: string | null;
  created_at: string;
  /** Some deployments annotate with actor username; tolerate missing. */
  actor?: string | null;
}

@Component({
  selector: 'app-audit-trail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TimeAgoPipe,
    IntlDateTimePipe,
  ],
  template: `
    <section class="at">
      <header class="at-head">
        <mat-icon aria-hidden="true">history</mat-icon>
        <h3 class="at-title">Audit trail</h3>
      </header>
      @if (loading()) {
        <div class="at-spinner"><mat-spinner diameter="24" /></div>
      } @else if (entries().length === 0) {
        <p class="at-empty">No audit history yet for this {{ targetType }}.</p>
      } @else {
        <ol class="at-list">
          @for (e of entries(); track e.id) {
            <li class="at-item">
              <span class="at-dot" aria-hidden="true"></span>
              <div class="at-body">
                <span class="at-action">{{ e.action }}</span>
                @if (e.actor) {
                  <span class="at-actor">by {{ e.actor }}</span>
                }
                <span
                  class="at-time"
                  [title]="e.created_at | intlDateTime"
                >{{ e.created_at | timeAgo }}</span>
              </div>
            </li>
          }
        </ol>
      }
    </section>
  `,
  styles: [`
    .at-head {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
    }
    .at-head mat-icon { color: var(--color-primary); }
    .at-title {
      margin: 0;
      font-size: 13px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .at-list {
      list-style: none;
      margin: 0;
      padding: 0 0 0 12px;
      border-left: 2px solid var(--color-border-faint);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .at-item {
      position: relative;
      padding-left: 8px;
    }
    .at-dot {
      position: absolute;
      left: -17px;
      top: 4px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--color-primary);
    }
    .at-body {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      font-size: 12px;
      line-height: 1.4;
    }
    .at-action {
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .at-actor {
      color: var(--color-text-secondary);
    }
    .at-time {
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
      cursor: help;
    }
    .at-empty {
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
      margin: 0;
    }
    .at-spinner {
      display: flex;
      justify-content: center;
      padding: 12px 0;
    }
  `],
})
export class AuditTrailComponent implements OnChanges {
  @Input({ required: true }) targetType = '';
  @Input({ required: true }) targetId: string | number = '';

  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly entries = signal<readonly AuditEntry[]>([]);

  ngOnChanges(): void {
    if (!this.targetType || !this.targetId) return;
    this.loading.set(true);
    const params = new HttpParams()
      .set('target_type', this.targetType)
      .set('target_id', String(this.targetId));
    this.http
      .get<AuditEntry[] | { results?: AuditEntry[] }>('/api/audit-entries/', { params })
      .pipe(
        catchError(() => of<AuditEntry[]>([])),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((raw) => {
        this.loading.set(false);
        const arr = Array.isArray(raw)
          ? raw
          : ((raw as { results?: AuditEntry[] })?.results ?? []);
        this.entries.set(
          [...arr].sort((a, b) => b.created_at.localeCompare(a.created_at)),
        );
      });
  }
}
