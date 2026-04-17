import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { GuidedTourService, DASHBOARD_TOUR } from '../../core/services/guided-tour.service';

/**
 * Phase D3 / Gap 171 — First-time Welcome card.
 *
 * Renders only on the user's first dashboard visit. Once dismissed
 * (or once the user clicks "Take the tour"), the card hides itself
 * permanently — a returning operator never sees it again.
 *
 * Persistence key intentionally distinct from the GuidedTourService's
 * "completed" flag so the card and the tour can be re-triggered
 * independently.
 */

const SEEN_KEY = 'xfil_welcome_card_seen';

@Component({
  selector: 'app-welcome-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule, MatButtonModule],
  template: `
    @if (visible()) {
      <mat-card class="wc-card">
        <mat-card-header>
          <mat-icon mat-card-avatar class="wc-avatar">waving_hand</mat-icon>
          <mat-card-title>Welcome to XF Internal Linker</mat-card-title>
          <mat-card-subtitle>You're seeing this once on your first visit</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p>
            This dashboard is your at-a-glance view of the internal-linking system:
            what's running, what needs attention, and what to do next. The cards
            below explain what they do — most have a "Why am I seeing this?" footer
            and an info icon for definitions.
          </p>
          <p>
            New here? Take the 60-second guided tour. You can replay it any time
            from the toolbar's 🗺 button.
          </p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-flat-button color="primary" type="button" (click)="takeTour()">
            <mat-icon>tour</mat-icon>
            Take the tour
          </button>
          <button mat-button type="button" (click)="dismiss()">
            Skip for now
          </button>
        </mat-card-actions>
      </mat-card>
    }
  `,
  styles: [`
    .wc-card {
      border-left: 4px solid var(--color-primary);
    }
    .wc-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    p {
      margin: 0 0 12px;
      font-size: 14px;
      line-height: 1.55;
      color: var(--color-text-primary);
    }
    p:last-child { margin-bottom: 0; }
  `],
})
export class WelcomeCardComponent implements OnInit {
  private readonly tour = inject(GuidedTourService);
  readonly visible = signal(false);

  ngOnInit(): void {
    try {
      this.visible.set(localStorage.getItem(SEEN_KEY) !== '1');
    } catch {
      this.visible.set(true);
    }
  }

  takeTour(): void {
    this.dismiss();
    this.tour.start(DASHBOARD_TOUR);
  }

  dismiss(): void {
    try { localStorage.setItem(SEEN_KEY, '1'); } catch { /* no-op */ }
    this.visible.set(false);
  }
}
