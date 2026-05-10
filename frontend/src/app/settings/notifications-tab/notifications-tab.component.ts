/**
 * NotificationsTabComponent — Settings tab 5 (Notifications).
 *
 * Extracted from the legacy 4,732-line `SettingsComponent` per the plan in
 * `frontend/src/app/settings/SETTINGS-SPLIT-PLAN.md` (AutoIssue #33).
 *
 * Owns its own state, save flow, and load flow. Emits `dirtyChanged` when
 * any preference toggle changes, so the parent component's existing
 * `HasUnsavedChanges` guard still fires correctly.
 *
 * Behaviour-preserving move: the four cards (alert delivery, quiet hours,
 * event subscriptions, send test alert) and their bindings are unchanged.
 */
import { ChangeDetectionStrategy, Component, DestroyRef, EventEmitter, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  NotificationPreferences,
  NotificationService,
} from '../../core/services/notification.service';
import { DesktopNotificationService } from '../../core/services/desktop-notification.service';
import { AudioCueService } from '../../core/services/audio-cue.service';

@Component({
  selector: 'app-notifications-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
  ],
  templateUrl: './notifications-tab.component.html',
  styleUrls: ['./notifications-tab.component.scss'],
})
export class NotificationsTabComponent implements OnInit {
  private notifSvc = inject(NotificationService);
  readonly desktopSvc = inject(DesktopNotificationService);
  private audioSvc = inject(AudioCueService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  /**
   * Fires `true` whenever the user touches any preference, `false` after a
   * successful save. Parent component (`SettingsComponent`) listens so the
   * existing isDirty / unsaved-changes-guard signal continues to work.
   */
  @Output() dirtyChanged = new EventEmitter<boolean>();

  readonly savingNotifPrefs = signal(false);
  readonly testingNotification = signal(false);

  /**
   * Defaults match the original parent-component shape exactly so the
   * dropdowns are not blank during the initial render before
   * `loadPreferences()` returns.
   */
  notifPrefs: NotificationPreferences = {
    desktop_enabled: true,
    sound_enabled: true,
    quiet_hours_enabled: false,
    quiet_hours_start: '22:00',
    quiet_hours_end: '07:00',
    min_desktop_severity: 'warning',
    min_sound_severity: 'error',
    enable_job_completed: true,
    enable_job_failed: true,
    enable_job_stalled: true,
    enable_model_status: true,
    enable_gsc_spikes: true,
    toast_enabled: true,
    toast_min_severity: 'warning',
    duplicate_cooldown_seconds: 900,
    job_stalled_default_minutes: 15,
    gsc_spike_min_impressions_delta: 50,
    gsc_spike_min_clicks_delta: 5,
    gsc_spike_min_relative_lift: 0.5,
  };

  ngOnInit(): void {
    this.notifSvc.loadPreferences()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((data) => {
        this.notifPrefs = { ...this.notifPrefs, ...data };
      });
  }

  /** Bound to every form-field `(ngModelChange)` so dirty signals propagate. */
  markDirty(): void {
    this.dirtyChanged.emit(true);
  }

  saveNotifPrefs(): void {
    this.savingNotifPrefs.set(true);
    this.notifSvc.savePreferences(this.notifPrefs)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (saved) => {
          this.notifPrefs = { ...this.notifPrefs, ...saved };
          this.savingNotifPrefs.set(false);
          this.dirtyChanged.emit(false);
          this.snack.open('Notification preferences saved.', undefined, { duration: 2500 });
        },
        error: () => {
          this.savingNotifPrefs.set(false);
          this.snack.open('Failed to save notification preferences.', 'Dismiss', { duration: 4000 });
        },
      });
  }

  sendTestNotification(severity: string): void {
    this.testingNotification.set(true);
    this.notifSvc.sendTestNotification(severity)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.testingNotification.set(false);
          this.snack.open('Test notification sent.', undefined, { duration: 2500 });
          this.audioSvc.playTone(severity === 'error' || severity === 'urgent' ? 'error' : 'warning');
        },
        error: () => {
          this.testingNotification.set(false);
          this.snack.open('Failed to send test notification.', 'Dismiss', { duration: 4000 });
        },
      });
  }

  async requestDesktopPermission(): Promise<void> {
    const result = await this.desktopSvc.requestPermission();
    if (result === 'granted') {
      this.snack.open('Desktop notifications enabled.', undefined, { duration: 2500 });
    } else if (result === 'denied') {
      this.snack.open('Desktop notifications blocked by the browser.', 'Dismiss', { duration: 5000 });
    }
  }
}
