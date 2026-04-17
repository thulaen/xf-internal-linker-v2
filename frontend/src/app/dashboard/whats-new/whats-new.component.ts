import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { CHANGELOG, ChangelogEntry } from './whats-new.data';

/**
 * Phase D3 / Gap 187 — "What's new since your last login" changelog.
 *
 * Filters CHANGELOG against the last-visit timestamp written by
 * personal-bar (`xfil_last_visit`). If the user is brand new (no
 * timestamp), shows the most recent two entries so first-time
 * operators see what shipped without being overwhelmed.
 *
 * Click "Mark as read" hides the card until the next NEW entry
 * arrives in the changelog.
 */

const SEEN_KEY = 'xfil_changelog_seen_iso';

@Component({
  selector: 'app-whats-new',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    RouterLink,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
  ],
  template: `
    @if (entries().length > 0) {
      <mat-card class="wn-card">
        <mat-card-header>
          <mat-icon mat-card-avatar class="wn-avatar">new_releases</mat-icon>
          <mat-card-title>What's new since your last visit</mat-card-title>
          <mat-card-subtitle>{{ entries().length }} update{{ entries().length === 1 ? '' : 's' }}</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <ul class="wn-list">
            @for (e of entries(); track e.date) {
              <li class="wn-item">
                <header class="wn-head">
                  <span class="wn-title">{{ e.title }}</span>
                  <span class="wn-date">{{ e.date | date:'mediumDate' }}</span>
                </header>
                <p class="wn-body">{{ e.body }}</p>
                @if (e.route) {
                  <a mat-button color="primary" [routerLink]="e.route">
                    Take me there
                    <mat-icon iconPositionEnd>arrow_forward</mat-icon>
                  </a>
                }
              </li>
            }
          </ul>
        </mat-card-content>
        <mat-card-actions>
          <button mat-button type="button" (click)="markRead()">
            Mark as read
          </button>
        </mat-card-actions>
      </mat-card>
    }
  `,
  styles: [`
    .wn-card { width: 100%; }
    .wn-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .wn-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .wn-item {
      padding: 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .wn-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 4px;
    }
    .wn-title {
      font-weight: 500;
      font-size: 14px;
      color: var(--color-text-primary);
    }
    .wn-date {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .wn-body {
      margin: 0 0 8px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--color-text-secondary);
    }
  `],
})
export class WhatsNewComponent implements OnInit {
  readonly entries = signal<readonly ChangelogEntry[]>([]);

  ngOnInit(): void {
    this.entries.set(this.computeEntries());
  }

  markRead(): void {
    const newest = CHANGELOG.reduce<string>(
      (acc, e) => (e.date > acc ? e.date : acc),
      '',
    );
    if (newest) {
      try { localStorage.setItem(SEEN_KEY, newest); } catch { /* no-op */ }
    }
    this.entries.set([]);
  }

  private computeEntries(): readonly ChangelogEntry[] {
    let cutoff = '';
    try {
      cutoff = localStorage.getItem(SEEN_KEY) ?? '';
    } catch {
      cutoff = '';
    }
    if (!cutoff) {
      // First-time visitor — fall back to the most-recent two entries
      // so they don't see a wall of historical news.
      return [...CHANGELOG]
        .sort((a, b) => b.date.localeCompare(a.date))
        .slice(0, 2);
    }
    return CHANGELOG
      .filter((e) => e.date > cutoff)
      .sort((a, b) => b.date.localeCompare(a.date));
  }
}
