import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D2 / Gap 72 — "Did you know?" Tips-of-the-Day card.
 *
 * Rotates one tip per visit (random pick from the not-yet-dismissed
 * pool). The user can dismiss the current tip permanently with "Don't
 * show again." When the pool is exhausted, the card hides itself.
 *
 * Tips are deliberately bite-sized — one keyboard shortcut, one config
 * idea, one "did you notice…" per tip. Power users hit "skip" and the
 * dashboard learns to stay quiet.
 */

interface Tip {
  id: string;
  text: string;
}

const TIP_BANK: readonly Tip[] = [
  { id: 'tip-cmd-k', text: 'Press Ctrl+K (or ⌘K on macOS) to open the global command palette from anywhere.' },
  { id: 'tip-shortcuts', text: 'Press the ? key to see every keyboard shortcut in one cheatsheet.' },
  { id: 'tip-glossary', text: 'Press Alt+G to open the glossary — every term used in the app, defined.' },
  { id: 'tip-tutorial', text: "Click the 🎓 icon in the top toolbar to turn on tutorial hints for every card." },
  { id: 'tip-explain', text: 'Click the ❓ icon in the toolbar to add inline definitions to dashboard metrics.' },
  { id: 'tip-pause-everything', text: 'The pause button in the toolbar pauses ALL workers at the next safe checkpoint.' },
  { id: 'tip-skip-link', text: 'Press Tab from page-load to reveal a "Skip to main content" link — saves keyboard users from tabbing through the toolbar.' },
  { id: 'tip-csv-export', text: 'Most data tables can be exported to CSV via the ⬇ download icon in the table header.' },
  { id: 'tip-print', text: 'Ctrl+P prints just the page content — the toolbar, sidenav, and FABs are stripped automatically.' },
  { id: 'tip-back-to-top', text: 'On long pages, the round arrow in the bottom-right scrolls back to the top.' },
  { id: 'tip-deep-link', text: "Many cards have a 'Go' button with a URL fragment — copy/paste the URL and it'll re-open the card highlighted." },
  { id: 'tip-share-dialog', text: 'Some dialogs add ?dialog=name to the URL — share the link and the recipient sees the same dialog open.' },
  { id: 'tip-runtime-mode', text: 'The "Performance Mode" chip in the dashboard top-right has Quiet/Balanced/Aggressive presets.' },
  { id: 'tip-ws-status', text: "The WS dot in the toolbar tells you whether real-time updates are flowing. Grey = offline, amber = reconnecting, green = live." },
  { id: 'tip-quarantine', text: 'A "quarantined" job has failed too many times. Open the Jobs page to inspect the root cause before retrying.' },
];

const DISMISSED_KEY = 'xfil_dismissed_tips';

@Component({
  selector: 'app-tips-of-day',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule, MatButtonModule],
  template: `
    @if (currentTip(); as t) {
      <mat-card class="tod-card">
        <mat-card-header>
          <mat-icon mat-card-avatar class="tod-avatar">tips_and_updates</mat-icon>
          <mat-card-title>Did you know?</mat-card-title>
          <mat-card-subtitle>One tip per visit · {{ remainingCount() }} left in the pool</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="tod-text">{{ t.text }}</p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-button type="button" (click)="next()">
            <mat-icon>refresh</mat-icon>
            Show another
          </button>
          <button mat-button type="button" color="warn" (click)="dismiss()">
            Don't show this again
          </button>
        </mat-card-actions>
      </mat-card>
    }
  `,
  styles: [`
    .tod-card { height: 100%; }
    .tod-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .tod-text {
      margin: 0;
      font-size: 14px;
      line-height: 1.55;
      color: var(--color-text-primary);
    }
  `],
})
export class TipsOfDayComponent implements OnInit {
  readonly currentTip = signal<Tip | null>(null);
  readonly remainingCount = signal<number>(0);

  ngOnInit(): void {
    this.pickNext();
  }

  next(): void {
    this.pickNext();
  }

  dismiss(): void {
    const t = this.currentTip();
    if (!t) return;
    const dismissed = this.readDismissed();
    dismissed.add(t.id);
    this.persistDismissed(dismissed);
    this.pickNext();
  }

  private pickNext(): void {
    const dismissed = this.readDismissed();
    const pool = TIP_BANK.filter((t) => !dismissed.has(t.id));
    this.remainingCount.set(pool.length);
    if (pool.length === 0) {
      this.currentTip.set(null);
      return;
    }
    // Random pick, but try not to immediately repeat the current tip.
    const current = this.currentTip();
    const candidates =
      pool.length > 1 && current
        ? pool.filter((t) => t.id !== current.id)
        : pool;
    const idx = Math.floor(Math.random() * candidates.length);
    this.currentTip.set(candidates[idx]);
  }

  private readDismissed(): Set<string> {
    try {
      const raw = localStorage.getItem(DISMISSED_KEY);
      if (!raw) return new Set();
      const arr = JSON.parse(raw) as string[];
      return new Set(Array.isArray(arr) ? arr : []);
    } catch {
      return new Set();
    }
  }

  private persistDismissed(set: Set<string>): void {
    try {
      localStorage.setItem(DISMISSED_KEY, JSON.stringify([...set]));
    } catch {
      // In-memory only.
    }
  }
}
