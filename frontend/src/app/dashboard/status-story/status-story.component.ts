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
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { catchError, of, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';

import { DashboardService, StatusStory } from '../dashboard.service';
import { ReadAloudComponent } from '../../shared/ui/read-aloud/read-aloud.component';

/**
 * Phase D1 / Gap 53 — "Status Story" card.
 *
 * A narrative summary in plain English, generated server-side.
 * Refreshes every 5 minutes to keep the wording honest without hammering
 * the backend. The card stays put on error — if the endpoint 500s, we
 * show the last-known story with a muted "last updated X ago" note
 * rather than an empty card.
 */
@Component({
  selector: 'app-status-story',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    ReadAloudComponent,
  ],
  template: `
    <mat-card class="status-story-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="story-avatar">article</mat-icon>
        <mat-card-title>Status Story</mat-card-title>
        <mat-card-subtitle>What's going on, in plain English</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @if (loading() && !story()) {
          <div class="story-spinner">
            <mat-spinner diameter="24"></mat-spinner>
          </div>
        } @else if (story(); as s) {
          <p class="story-headline">{{ s.headline }}</p>
          @if (errored()) {
            <p class="story-stale-hint">
              <mat-icon class="story-stale-icon">schedule</mat-icon>
              Last refreshed {{ freshnessLabel(s.generated_at) }}. Trying again
              in the background.
            </p>
          }
        } @else {
          <p class="story-empty">Couldn't reach the server. Try again shortly.</p>
        }
      </mat-card-content>
      <mat-card-actions>
        <button
          mat-button
          color="primary"
          type="button"
          [disabled]="loading()"
          (click)="refresh()"
        >
          <mat-icon>refresh</mat-icon>
          Refresh
        </button>
        <!-- Phase D2 / Gap 75 — TTS button. Hidden if browser lacks Web
             Speech API support; otherwise reads the headline aloud. -->
        @if (story(); as s) {
          <app-read-aloud
            [text]="s.headline"
            label="Read the status story aloud"
          />
        }
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    .status-story-card { height: 100%; }
    .story-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .story-headline {
      font-size: 15px;
      line-height: 1.55;
      color: var(--color-text-primary);
      margin: 8px 0 0;
    }
    .story-stale-hint {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      color: var(--color-text-secondary);
      margin: 12px 0 0;
    }
    .story-stale-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    .story-spinner {
      display: flex;
      justify-content: center;
      padding: 16px 0;
    }
    .story-empty {
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
      margin: 0;
    }
  `],
})
export class StatusStoryComponent implements OnInit {
  private readonly dash = inject(DashboardService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly visibilityGate = inject(VisibilityGateService);

  readonly story = signal<StatusStory | null>(null);
  readonly loading = signal(false);
  readonly errored = signal(false);

  ngOnInit(): void {
    // Initial fetch + 5-minute auto-refresh. Gated by
    // `VisibilityGateService` so hidden tabs and signed-out sessions
    // skip the poll. See docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(0, 5 * 60 * 1000).pipe(
          switchMap(() => {
            this.loading.set(true);
            return this.dash
              .getStatusStory()
              .pipe(catchError(() => of<StatusStory | null>(null)));
          }),
        ),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((story) => {
        this.loading.set(false);
        if (story) {
          this.story.set(story);
          this.errored.set(false);
        } else {
          // Keep the previous story visible so the card isn't blank.
          this.errored.set(true);
        }
      });
  }

  refresh(): void {
    this.loading.set(true);
    this.dash
      .getStatusStory()
      .pipe(
        catchError(() => of<StatusStory | null>(null)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((story) => {
        this.loading.set(false);
        if (story) {
          this.story.set(story);
          this.errored.set(false);
        } else {
          this.errored.set(true);
        }
      });
  }

  freshnessLabel(iso: string): string {
    const diffMs = Date.now() - Date.parse(iso);
    if (!Number.isFinite(diffMs) || diffMs < 0) return 'just now';
    const secs = Math.floor(diffMs / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    return `${hours}h ago`;
  }
}
