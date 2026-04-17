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
import { catchError, of, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';

import { AuthService } from '../../core/services/auth.service';

/**
 * Phase D3 / Gap 183 — Who's-on-shift widget.
 *
 * Best-effort multi-user presence — shows who else is currently
 * authenticated. Calls `/api/auth/active-users/` (a future backend
 * endpoint) every 60s; falls back to "you only" when the endpoint
 * doesn't exist (single-tenant deployment is the common case).
 *
 * The widget self-hides if the only active user is the current user
 * AND the endpoint returned 404, so single-operator deployments
 * never see a useless "just you" card.
 */

interface ActiveUser {
  username: string;
  last_seen: string;
}

@Component({
  selector: 'app-whos-on-shift',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule],
  template: `
    @if (visible()) {
      <mat-card class="ws-card">
        <mat-card-header>
          <mat-icon mat-card-avatar class="ws-avatar">people</mat-icon>
          <mat-card-title>Who's on shift</mat-card-title>
          <mat-card-subtitle>{{ users().length }} active in the last 5 minutes</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <ul class="ws-list">
            @for (u of users(); track u.username) {
              <li class="ws-row" [class.ws-self]="u.username === self()">
                <span class="ws-dot" aria-hidden="true"></span>
                <span class="ws-name">
                  {{ u.username }}{{ u.username === self() ? ' (you)' : '' }}
                </span>
                <span class="ws-time">{{ ago(u.last_seen) }}</span>
              </li>
            }
          </ul>
        </mat-card-content>
      </mat-card>
    }
  `,
  styles: [`
    .ws-card { height: 100%; }
    .ws-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .ws-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .ws-row {
      display: grid;
      grid-template-columns: 12px 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 6px 12px;
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .ws-row.ws-self {
      background: var(--color-bg-white);
      border: var(--card-border);
    }
    .ws-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--color-success, #1e8e3e);
    }
    .ws-name {
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .ws-time {
      font-size: 11px;
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
    }
  `],
})
export class WhosOnShiftComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly users = signal<readonly ActiveUser[]>([]);
  readonly self = signal<string>('');
  /** Hide entirely on single-tenant deployments where the endpoint
   *  doesn't exist OR the only user is the current operator. */
  readonly visible = signal<boolean>(false);

  ngOnInit(): void {
    this.auth.currentUser$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => this.self.set(u?.username ?? ''));

    timer(0, 60_000)
      .pipe(
        switchMap(() =>
          this.http
            .get<ActiveUser[]>('/api/auth/active-users/')
            .pipe(catchError(() => of<ActiveUser[] | null>(null))),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((list) => {
        if (!Array.isArray(list)) {
          // Endpoint unavailable — hide the card entirely.
          this.visible.set(false);
          return;
        }
        this.users.set(list);
        // Show only when at least one OTHER user is active alongside us.
        const hasOthers = list.some((u) => u.username !== this.self());
        this.visible.set(hasOthers);
      });
  }

  ago(iso: string): string {
    const ms = Date.now() - Date.parse(iso);
    if (!Number.isFinite(ms) || ms < 0) return '';
    const mins = Math.floor(ms / 60_000);
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ago`;
  }
}
