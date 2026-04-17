import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnInit,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { ContentSnippet } from './content-cards.data';

/**
 * Phase D3 — generic rotating-content card. Backs four gaps:
 *   - Gap 159 Latest Wins
 *   - Gap 160 Things to Avoid
 *   - Gap 185 Pitfall of the day
 *   - Gap 186 Motivational quote
 *
 * Each instance is configured by inputs:
 *   - title / subtitle / icon / accent
 *   - bank: the array of snippets to rotate through
 *   - storageKey: localStorage namespace for "seen" + "favorited"
 *   - rotation: 'random' (per visit) | 'daily' (one per local day)
 *
 * Same chrome, different content — keeps the four gaps visually
 * consistent without four near-identical components.
 */
@Component({
  selector: 'app-rotating-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule, MatButtonModule],
  template: `
    @if (current(); as snip) {
      <mat-card class="rc-card" [class]="'rc-accent-' + accent">
        <mat-card-header>
          <mat-icon mat-card-avatar class="rc-avatar">{{ icon }}</mat-icon>
          <mat-card-title>{{ title }}</mat-card-title>
          @if (subtitle) {
            <mat-card-subtitle>{{ subtitle }}</mat-card-subtitle>
          }
        </mat-card-header>
        <mat-card-content>
          <p class="rc-text">{{ snip.text }}</p>
          @if (snip.attribution) {
            <p class="rc-attribution">— {{ snip.attribution }}</p>
          }
        </mat-card-content>
        @if (showControls) {
          <mat-card-actions>
            <button mat-button type="button" (click)="next()">
              <mat-icon>refresh</mat-icon>
              Show another
            </button>
          </mat-card-actions>
        }
      </mat-card>
    }
  `,
  styles: [`
    .rc-card { height: 100%; }
    .rc-accent-good .rc-avatar { background: var(--color-success, #1e8e3e); color: #fff; }
    .rc-accent-warn .rc-avatar { background: var(--color-warning, #f9ab00); color: #fff; }
    .rc-accent-bad  .rc-avatar { background: var(--color-error, #d93025); color: #fff; }
    .rc-accent-info .rc-avatar { background: var(--color-primary, #1a73e8); color: #fff; }
    .rc-text {
      margin: 0;
      font-size: 14px;
      line-height: 1.55;
      color: var(--color-text-primary);
    }
    .rc-attribution {
      margin: 8px 0 0;
      font-size: 12px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
  `],
})
export class RotatingCardComponent implements OnInit {
  /** Card chrome */
  @Input({ required: true }) title = '';
  @Input() subtitle = '';
  @Input({ required: true }) icon = 'lightbulb';
  @Input() accent: 'good' | 'warn' | 'bad' | 'info' = 'info';
  /** Where to look up snippets. */
  @Input({ required: true }) bank: readonly ContentSnippet[] = [];
  /** localStorage namespace — picks "last seen" key + day key. */
  @Input({ required: true }) storageKey = '';
  /** 'random' = re-roll on each visit. 'daily' = one per local day. */
  @Input() rotation: 'random' | 'daily' = 'random';
  /** Whether to render the "show another" button. Hide for the
   *  daily-rotation cards (pitfalls, quotes) where re-rolling
   *  contradicts the once-per-day framing. */
  @Input() showControls = true;

  readonly current = signal<ContentSnippet | null>(null);

  ngOnInit(): void {
    if (this.bank.length === 0) return;
    if (this.rotation === 'daily') {
      this.current.set(this.pickForToday());
    } else {
      this.current.set(this.pickRandom(this.current()?.id));
    }
  }

  next(): void {
    if (this.bank.length === 0) return;
    this.current.set(this.pickRandom(this.current()?.id));
  }

  // ── pickers ────────────────────────────────────────────────────────

  private pickRandom(skipId?: string): ContentSnippet {
    const candidates = skipId && this.bank.length > 1
      ? this.bank.filter((s) => s.id !== skipId)
      : this.bank;
    const idx = Math.floor(Math.random() * candidates.length);
    return candidates[idx];
  }

  private pickForToday(): ContentSnippet {
    const today = this.todayKey();
    const epochDays = Math.floor(Date.parse(today + 'T00:00:00Z') / 86_400_000);
    const idx = ((epochDays % this.bank.length) + this.bank.length) % this.bank.length;
    return this.bank[idx];
  }

  private todayKey(): string {
    const d = new Date();
    return `${d.getFullYear()}-${(d.getMonth() + 1)
      .toString()
      .padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`;
  }
}
