import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  NgZone,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DatePipe } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { interval } from 'rxjs';

import { AuthService } from '../../core/services/auth.service';

/**
 * Phase D3 — combined personal-bar widget covering:
 *   - Gap 152: Big clock + date (always-visible local time)
 *   - Gap 154: Personalised greeting ("Good morning, Alice")
 *   - Gap 179: "Your last session" footer ("3h ago — you approved 12")
 *   - Gap 181: Daily streak counter ("7 days in a row")
 *
 * Bundled into one component because they all live in the same
 * dashboard-top horizontal strip. Splitting them would mean four
 * grids of one card each — not how a noob expects "personal stuff" to
 * read on a dashboard.
 *
 * Streak + last-session data come from localStorage. The streak share
 * the same anchor key the daily quiz uses (`xfil_quiz_streak`) so the
 * two read consistently.
 */

const VISIT_KEY = 'xfil_last_visit';
const VISIT_DETAIL_KEY = 'xfil_last_visit_detail';
const STREAK_KEY = 'xfil_visit_streak';
const STREAK_LAST_DAY_KEY = 'xfil_visit_streak_last_day';

interface VisitDetail {
  ts: number;
  approved?: number;
  reviewed?: number;
}

@Component({
  selector: 'app-personal-bar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DatePipe, MatIconModule],
  template: `
    <section class="pb">
      <div class="pb-greeting">
        <span class="pb-greet-line">{{ greeting() }}{{ username() ? ', ' + username() : '' }}.</span>
        @if (lastVisitLabel(); as l) {
          <span class="pb-last">
            <mat-icon class="pb-icon">history</mat-icon>
            {{ l }}
          </span>
        }
      </div>

      <div class="pb-clock" aria-label="Current local time">
        <span class="pb-time">{{ now() | date:'HH:mm' }}</span>
        <span class="pb-date">{{ now() | date:'EEEE, MMM d' }}</span>
      </div>

      @if (streak() > 0) {
        <div class="pb-streak" [class.pb-streak-hot]="streak() >= 7" aria-label="Daily streak">
          <mat-icon class="pb-streak-icon">local_fire_department</mat-icon>
          <span class="pb-streak-count">{{ streak() }}</span>
          <span class="pb-streak-label">
            day{{ streak() === 1 ? '' : 's' }} in a row
          </span>
        </div>
      }
    </section>
  `,
  styles: [`
    .pb {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 16px;
      align-items: center;
      padding: 12px 16px;
      background: var(--color-bg-white);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
    }
    .pb-greeting {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .pb-greet-line {
      font-size: 18px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .pb-last {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .pb-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    .pb-clock {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 2px;
    }
    .pb-time {
      font-size: 26px;
      font-weight: 500;
      color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
      letter-spacing: 1px;
    }
    .pb-date {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .pb-streak {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0;
      padding: 6px 12px;
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
      min-width: 80px;
    }
    .pb-streak-hot {
      background: var(--color-warning-light, rgba(249, 171, 0, 0.12));
    }
    .pb-streak-icon {
      color: var(--color-warning, #f9ab00);
      font-size: 22px;
      width: 22px;
      height: 22px;
    }
    .pb-streak-hot .pb-streak-icon {
      color: var(--color-error, #d93025);
    }
    .pb-streak-count {
      font-size: 18px;
      font-weight: 600;
      color: var(--color-text-primary);
      line-height: 1;
    }
    .pb-streak-label {
      font-size: 10px;
      color: var(--color-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.4px;
      line-height: 1.4;
    }
    @media (max-width: 720px) {
      .pb { grid-template-columns: 1fr; }
      .pb-clock, .pb-streak { align-self: flex-start; }
    }
  `],
})
export class PersonalBarComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly ngZone = inject(NgZone);
  private readonly cdr = inject(ChangeDetectorRef);

  readonly now = signal<Date>(new Date());
  readonly username = signal<string>('');
  readonly streak = signal<number>(0);
  readonly lastVisitLabel = signal<string>('');

  ngOnInit(): void {
    // Live-tick the clock once per second. Runs OUTSIDE the Angular
    // zone so the tick itself does not schedule a global change-detection
    // pass across every `OnPush` sibling on the dashboard. We still need
    // the view to update, so we `markForCheck` after the signal set —
    // this asks Angular to re-check only this component's path on the
    // next CD pass (which is piggy-backed on any other event already in
    // flight). See docs/PERFORMANCE.md §13.
    this.ngZone.runOutsideAngular(() => {
      interval(1000)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => {
          this.now.set(new Date());
          this.cdr.markForCheck();
        });
    });

    this.auth.currentUser$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((user) => this.username.set(user?.username ?? ''));

    // Read last-visit + streak from storage BEFORE we record THIS visit,
    // so the user sees data about their previous session.
    const lastDetail = this.readLastVisit();
    if (lastDetail) {
      this.lastVisitLabel.set(this.formatLastVisit(lastDetail));
    }
    this.streak.set(this.bumpAndReadStreak());

    // Stamp this visit so it becomes the next session's "last visit".
    this.recordThisVisit();
  }

  greeting(): string {
    const h = this.now().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    if (h < 21) return 'Good evening';
    return 'Working late';
  }

  // ── persistence helpers ────────────────────────────────────────────

  private readLastVisit(): VisitDetail | null {
    try {
      const raw = localStorage.getItem(VISIT_DETAIL_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as VisitDetail;
      if (!parsed?.ts || typeof parsed.ts !== 'number') return null;
      return parsed;
    } catch {
      return null;
    }
  }

  private recordThisVisit(): void {
    try {
      const detail: VisitDetail = { ts: Date.now() };
      localStorage.setItem(VISIT_KEY, String(detail.ts));
      localStorage.setItem(VISIT_DETAIL_KEY, JSON.stringify(detail));
    } catch {
      // Private mode — best-effort.
    }
  }

  private formatLastVisit(detail: VisitDetail): string {
    const diffMs = Date.now() - detail.ts;
    if (diffMs < 0) return '';
    const mins = Math.floor(diffMs / 60_000);
    if (mins < 1) return 'Welcome back — just now.';
    if (mins < 60) return `Welcome back — last seen ${mins}m ago.`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `Welcome back — last seen ${hours}h ago.`;
    const days = Math.floor(hours / 24);
    if (days === 1) return 'Welcome back — last seen yesterday.';
    return `Welcome back — last seen ${days} days ago.`;
  }

  /** Increment-or-reset the visit streak and return the new value. */
  private bumpAndReadStreak(): number {
    try {
      const today = this.todayKey();
      const last = localStorage.getItem(STREAK_LAST_DAY_KEY);
      const current = Number.parseInt(localStorage.getItem(STREAK_KEY) ?? '0', 10) || 0;
      if (last === today) return current; // already bumped today

      // What was yesterday's key?
      const d = new Date();
      d.setDate(d.getDate() - 1);
      const yesterday = `${d.getFullYear()}-${(d.getMonth() + 1)
        .toString()
        .padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`;

      const next = last === yesterday ? current + 1 : 1;
      localStorage.setItem(STREAK_KEY, String(next));
      localStorage.setItem(STREAK_LAST_DAY_KEY, today);
      return next;
    } catch {
      return 0;
    }
  }

  private todayKey(): string {
    const d = new Date();
    return `${d.getFullYear()}-${(d.getMonth() + 1)
      .toString()
      .padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`;
  }
}
