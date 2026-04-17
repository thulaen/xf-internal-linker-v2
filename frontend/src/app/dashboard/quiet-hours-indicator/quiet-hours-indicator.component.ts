import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { interval } from 'rxjs';

/**
 * Phase D3 / Gap 182 — Quiet-hours indicator.
 *
 * Shows whether the current local time falls within the operator's
 * configured quiet window. During quiet hours, non-urgent
 * notifications and beep-style toasts should self-mute (consumers
 * read the same `isQuiet()` signal exposed here).
 *
 * Configuration is local-only (storage keys
 * `xfil_quiet_hours_start` / `xfil_quiet_hours_end`). A future
 * session can sync to the user's notification preferences in the
 * backend; until then this is a noob-friendly client-side toggle.
 */

const START_KEY = 'xfil_quiet_hours_start';
const END_KEY = 'xfil_quiet_hours_end';
const ENABLED_KEY = 'xfil_quiet_hours_enabled';

@Component({
  selector: 'app-quiet-hours-indicator',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <mat-card class="qh-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="qh-avatar">bedtime</mat-icon>
        <mat-card-title>Quiet hours</mat-card-title>
        <mat-card-subtitle>{{ statusLabel() }}</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <div class="qh-status" [class.qh-active]="isQuiet()">
          <mat-icon>{{ isQuiet() ? 'do_not_disturb_on' : 'notifications_active' }}</mat-icon>
          <span>{{ isQuiet() ? 'Currently in quiet hours' : 'Currently in working hours' }}</span>
        </div>

        @if (editing()) {
          <form (submit)="save($event)" class="qh-form">
            <mat-form-field appearance="outline" class="qh-field">
              <mat-label>Start</mat-label>
              <input matInput type="time" autocomplete="off" [(ngModel)]="startDraft" name="qh-start" />
            </mat-form-field>
            <mat-form-field appearance="outline" class="qh-field">
              <mat-label>End</mat-label>
              <input matInput type="time" autocomplete="off" [(ngModel)]="endDraft" name="qh-end" />
            </mat-form-field>
            <button mat-flat-button color="primary" type="submit">Save</button>
            <button mat-button type="button" (click)="cancelEdit()">Cancel</button>
          </form>
        } @else {
          <p class="qh-window">
            Quiet from <strong>{{ start() }}</strong> to <strong>{{ end() }}</strong> local time.
          </p>
          <button mat-button type="button" (click)="startEdit()">
            <mat-icon>edit</mat-icon>
            Change window
          </button>
          <button mat-button type="button" (click)="toggleEnabled()">
            {{ enabled() ? 'Turn off' : 'Turn on' }}
          </button>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .qh-card { height: 100%; }
    .qh-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .qh-status {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
      font-size: 13px;
      color: var(--color-text-primary);
      margin-bottom: 8px;
    }
    .qh-status.qh-active {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .qh-status.qh-active mat-icon { color: var(--color-on-primary, #ffffff); }
    .qh-window {
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .qh-form {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      flex-wrap: wrap;
    }
    .qh-field { width: 130px; }
  `],
})
export class QuietHoursIndicatorComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);

  readonly enabled = signal<boolean>(true);
  readonly start = signal<string>('22:00');
  readonly end = signal<string>('07:00');
  readonly editing = signal<boolean>(false);
  readonly now = signal<Date>(new Date());

  startDraft = '22:00';
  endDraft = '07:00';

  readonly isQuiet = computed<boolean>(() => {
    if (!this.enabled()) return false;
    const n = this.now();
    const minsNow = n.getHours() * 60 + n.getMinutes();
    const startMins = this.timeToMinutes(this.start());
    const endMins = this.timeToMinutes(this.end());
    if (startMins === endMins) return false;
    if (startMins < endMins) {
      return minsNow >= startMins && minsNow < endMins;
    }
    // Crosses midnight (e.g. 22:00 → 07:00).
    return minsNow >= startMins || minsNow < endMins;
  });

  readonly statusLabel = computed<string>(() =>
    this.enabled()
      ? 'Mute non-urgent notifications inside the window'
      : 'Disabled — all notifications fire normally',
  );

  ngOnInit(): void {
    this.loadFromStorage();
    interval(60_000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.now.set(new Date()));
  }

  startEdit(): void {
    this.startDraft = this.start();
    this.endDraft = this.end();
    this.editing.set(true);
  }

  cancelEdit(): void {
    this.editing.set(false);
  }

  save(event: Event): void {
    event.preventDefault();
    if (!this.startDraft || !this.endDraft) return;
    this.start.set(this.startDraft);
    this.end.set(this.endDraft);
    try {
      localStorage.setItem(START_KEY, this.startDraft);
      localStorage.setItem(END_KEY, this.endDraft);
    } catch {
      // No-op.
    }
    this.editing.set(false);
  }

  toggleEnabled(): void {
    const next = !this.enabled();
    this.enabled.set(next);
    try { localStorage.setItem(ENABLED_KEY, next ? '1' : '0'); } catch { /* no-op */ }
  }

  // ── helpers ────────────────────────────────────────────────────────

  private loadFromStorage(): void {
    try {
      const en = localStorage.getItem(ENABLED_KEY);
      this.enabled.set(en === null ? true : en === '1');
      const s = localStorage.getItem(START_KEY);
      const e = localStorage.getItem(END_KEY);
      if (s && /^\d{2}:\d{2}$/.test(s)) this.start.set(s);
      if (e && /^\d{2}:\d{2}$/.test(e)) this.end.set(e);
    } catch {
      // No-op.
    }
  }

  private timeToMinutes(t: string): number {
    const [h, m] = t.split(':').map((p) => Number.parseInt(p, 10));
    if (Number.isNaN(h) || Number.isNaN(m)) return 0;
    return h * 60 + m;
  }
}
