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
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';

/**
 * Phase D2 / Gap 76 — Weekly digest opt-in card.
 *
 * Lets the operator toggle a weekly email digest from the dashboard
 * without leaving for Settings. Persists the preference under the
 * existing notifications-prefs key the rest of the app already uses
 * (`xfil_weekly_digest`); future server sync can read the same key.
 *
 * Backend hookup is out of scope for this gap — when the toggle is
 * flipped we POST to `/api/notifications/weekly-digest/` (best-effort,
 * silent on 404 so the UI stays useful even before the endpoint
 * exists). The localStorage write always succeeds.
 *
 * Distinct from the full Notification Preferences screen (which lives
 * under Settings → Notifications and exposes per-channel granular
 * controls) — this is the noob-friendly "yes / no / when" switch.
 */

interface DigestPrefs {
  enabled: boolean;
  day: 'monday' | 'wednesday' | 'friday' | 'sunday';
  time: '06:00' | '08:00' | '12:00' | '18:00';
}

const STORAGE_KEY = 'xfil_weekly_digest';
const DAYS: { value: DigestPrefs['day']; label: string }[] = [
  { value: 'monday', label: 'Monday morning' },
  { value: 'wednesday', label: 'Wednesday morning' },
  { value: 'friday', label: 'Friday afternoon' },
  { value: 'sunday', label: 'Sunday evening' },
];
const TIMES: { value: DigestPrefs['time']; label: string }[] = [
  { value: '06:00', label: '6:00 AM' },
  { value: '08:00', label: '8:00 AM' },
  { value: '12:00', label: 'Noon' },
  { value: '18:00', label: '6:00 PM' },
];

const DEFAULTS: DigestPrefs = {
  enabled: false,
  day: 'monday',
  time: '08:00',
};

@Component({
  selector: 'app-weekly-digest-optin',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatSlideToggleModule,
    MatFormFieldModule,
    MatSelectModule,
  ],
  template: `
    <mat-card class="wd-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="wd-avatar">mark_email_read</mat-icon>
        <mat-card-title>Weekly digest</mat-card-title>
        <mat-card-subtitle>Plain-English summary in your inbox</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <mat-slide-toggle
          color="primary"
          class="wd-toggle"
          [checked]="prefs().enabled"
          (change)="setEnabled($event.checked)"
        >
          {{ prefs().enabled ? 'Digest is ON' : 'Digest is OFF' }}
        </mat-slide-toggle>
        <p class="wd-note">
          Weekly digest summarises last week's approvals, broken-link
          findings, top alerts, and pipeline runs in one short email.
        </p>

        @if (prefs().enabled) {
          <div class="wd-knobs">
            <mat-form-field appearance="outline" class="wd-field">
              <mat-label>Send on</mat-label>
              <mat-select
                [(value)]="dayValue"
                (valueChange)="setDay($event)"
              >
                @for (d of days; track d.value) {
                  <mat-option [value]="d.value">{{ d.label }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="wd-field">
              <mat-label>Time of day</mat-label>
              <mat-select
                [(value)]="timeValue"
                (valueChange)="setTime($event)"
              >
                @for (t of times; track t.value) {
                  <mat-option [value]="t.value">{{ t.label }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .wd-card { height: 100%; }
    .wd-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .wd-toggle { margin: 0 0 8px; }
    .wd-note {
      margin: 0 0 16px;
      font-size: 12px;
      line-height: 1.5;
      color: var(--color-text-secondary);
    }
    .wd-knobs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .wd-field { width: 100%; }
  `],
})
export class WeeklyDigestOptinComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly snack = inject(MatSnackBar);

  readonly days = DAYS;
  readonly times = TIMES;

  readonly prefs = signal<DigestPrefs>(DEFAULTS);
  dayValue: DigestPrefs['day'] = DEFAULTS.day;
  timeValue: DigestPrefs['time'] = DEFAULTS.time;

  ngOnInit(): void {
    const loaded = this.read();
    this.prefs.set(loaded);
    this.dayValue = loaded.day;
    this.timeValue = loaded.time;
  }

  setEnabled(next: boolean): void {
    this.update({ enabled: next });
    this.snack.open(
      next ? 'Weekly digest scheduled.' : 'Weekly digest cancelled.',
      'OK',
      { duration: 3000 },
    );
  }

  setDay(next: DigestPrefs['day']): void {
    this.update({ day: next });
  }

  setTime(next: DigestPrefs['time']): void {
    this.update({ time: next });
  }

  private update(partial: Partial<DigestPrefs>): void {
    const merged = { ...this.prefs(), ...partial };
    this.prefs.set(merged);
    this.persist(merged);
    this.bestEffortSync(merged);
  }

  // ── persistence ────────────────────────────────────────────────────

  private read(): DigestPrefs {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { ...DEFAULTS };
      const parsed = JSON.parse(raw) as Partial<DigestPrefs>;
      return {
        enabled: !!parsed.enabled,
        day: (parsed.day as DigestPrefs['day']) ?? DEFAULTS.day,
        time: (parsed.time as DigestPrefs['time']) ?? DEFAULTS.time,
      };
    } catch {
      return { ...DEFAULTS };
    }
  }

  private persist(prefs: DigestPrefs): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // In-memory only.
    }
  }

  /** Fire-and-forget sync to the backend if the endpoint exists.
   *  Silent on any error — local prefs are the source of truth until
   *  the server-side digest scheduler ships. */
  private bestEffortSync(prefs: DigestPrefs): void {
    try {
      fetch('/api/notifications/weekly-digest/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prefs),
      }).catch(() => {
        /* best-effort */
      });
    } catch {
      // No-op.
    }
  }
}
