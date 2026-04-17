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
import { NavigationEnd, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { filter } from 'rxjs';

/**
 * Phase D3 / Gap 153 — "You are here: Dashboard" thin context strip.
 *
 * A persistent breadcrumb-lite strip that sits ABOVE the page content
 * and tells the user, in plain English, where they are right now. The
 * sidenav already shows the active route in its menu, but noobs scan
 * the page body, not the chrome — this strip puts the answer where
 * they're looking.
 *
 * Distinct from a true breadcrumb (Gap 143, which appears for >2-level
 * deep pages and lists ancestors). This is a single-line "you are
 * here" label that always reflects the top-level route.
 */

const ROUTE_LABELS: Record<string, { label: string; icon: string }> = {
  '/': { label: 'Dashboard', icon: 'dashboard' },
  '/dashboard': { label: 'Dashboard', icon: 'dashboard' },
  '/review': { label: 'Review queue', icon: 'rate_review' },
  '/link-health': { label: 'Link Health', icon: 'link_off' },
  '/graph': { label: 'Link Graph', icon: 'account_tree' },
  '/behavioral-hubs': { label: 'Behavioral Hubs', icon: 'hub' },
  '/analytics': { label: 'Analytics', icon: 'bar_chart' },
  '/jobs': { label: 'Jobs', icon: 'pending_actions' },
  '/health': { label: 'System Health', icon: 'health_and_safety' },
  '/settings': { label: 'Settings', icon: 'settings' },
  '/alerts': { label: 'Alerts', icon: 'notifications' },
  '/crawler': { label: 'Web Crawler', icon: 'travel_explore' },
  '/error-log': { label: 'Error Log', icon: 'bug_report' },
  '/performance': { label: 'Performance', icon: 'speed' },
  '/login': { label: 'Sign in', icon: 'login' },
};

@Component({
  selector: 'app-you-are-here',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule],
  template: `
    <div class="yah" role="status" aria-live="polite">
      <span class="yah-prefix">You are here:</span>
      <mat-icon class="yah-icon" aria-hidden="true">{{ current().icon }}</mat-icon>
      <span class="yah-label">{{ current().label }}</span>
    </div>
  `,
  styles: [`
    .yah {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      font-size: 12px;
      color: var(--color-text-secondary);
      background: var(--color-bg-faint);
      border-radius: var(--card-border-radius, 8px);
      border: var(--card-border);
      width: fit-content;
    }
    .yah-prefix {
      color: var(--color-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-size: 10px;
      font-weight: 500;
    }
    .yah-icon {
      color: var(--color-primary);
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .yah-label {
      color: var(--color-text-primary);
      font-weight: 500;
    }
  `],
})
export class YouAreHereComponent implements OnInit {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly current = signal<{ label: string; icon: string }>(this.lookup(this.router.url));

  ngOnInit(): void {
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => {
        this.current.set(this.lookup((e as NavigationEnd).urlAfterRedirects));
      });
  }

  private lookup(url: string): { label: string; icon: string } {
    const noQs = (url ?? '').split('?')[0].split('#')[0];
    const parts = noQs.split('/').filter(Boolean);
    const top = parts.length === 0 ? '/' : '/' + parts[0];
    return ROUTE_LABELS[top] ?? { label: top, icon: 'navigation' };
  }
}
