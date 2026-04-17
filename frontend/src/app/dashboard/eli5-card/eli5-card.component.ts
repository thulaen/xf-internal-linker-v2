import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { ELI5, Eli5Snippet } from './eli5.data';

/**
 * Phase D3 / Gap 176 — Explain Like I'm Five rotating card.
 *
 * One concept per visit, picked randomly from the ELI5 bank. The card
 * is intentionally distinct from the daily quiz (interactive) and the
 * tips card (operational hints) — this one is purely conceptual,
 * answering "why is this thing called X?" in five-year-old language.
 */
@Component({
  selector: 'app-eli5-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule, MatButtonModule],
  template: `
    @if (current(); as e) {
      <mat-card class="eli5-card">
        <mat-card-header>
          <mat-icon mat-card-avatar class="eli5-avatar">child_care</mat-icon>
          <mat-card-title>Explain like I'm 5</mat-card-title>
          <mat-card-subtitle>{{ e.topic }}</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="eli5-text">{{ e.text }}</p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-button type="button" (click)="next()">
            <mat-icon>refresh</mat-icon>
            Another concept
          </button>
        </mat-card-actions>
      </mat-card>
    }
  `,
  styles: [`
    .eli5-card { height: 100%; }
    .eli5-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .eli5-text {
      margin: 0;
      font-size: 14px;
      line-height: 1.6;
      color: var(--color-text-primary);
    }
  `],
})
export class Eli5CardComponent implements OnInit {
  readonly current = signal<Eli5Snippet | null>(null);

  ngOnInit(): void {
    this.next();
  }

  next(): void {
    const skip = this.current()?.id;
    const pool = skip ? ELI5.filter((e) => e.id !== skip) : [...ELI5];
    if (pool.length === 0) return;
    this.current.set(pool[Math.floor(Math.random() * pool.length)]);
  }
}
