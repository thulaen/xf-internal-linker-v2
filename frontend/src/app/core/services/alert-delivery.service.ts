/**
 * AlertDeliveryService — fans out new WebSocket alerts to toast, desktop, and sound.
 *
 * This service is injected in AppComponent so it starts at app boot.
 * It subscribes to NotificationService.newAlert$ and dispatches each
 * incoming alert to the three delivery channels according to the user's
 * saved preferences.
 */

import { Injectable, OnDestroy, inject } from '@angular/core';
import { Subscription } from 'rxjs';
import { AudioCueService } from './audio-cue.service';
import { DesktopNotificationService } from './desktop-notification.service';
import { NotificationPreferences, NotificationService, OperatorAlert } from './notification.service';
import { ToastService } from './toast.service';

@Injectable({ providedIn: 'root' })
export class AlertDeliveryService implements OnDestroy {
  private notifSvc = inject(NotificationService);
  private toastSvc = inject(ToastService);
  private desktopSvc = inject(DesktopNotificationService);
  private audioSvc = inject(AudioCueService);

  private prefs: NotificationPreferences | null = null;
  private sub: Subscription | null = null;

  /** Call once from AppComponent.ngOnInit(). */
  start(): void {
    // Load preferences on boot (best-effort — use defaults if unavailable)
    this.notifSvc.loadPreferences().subscribe({
      next: (p) => { this.prefs = p; },
      error: () => { this.prefs = null; },
    });

    this.sub = this.notifSvc.newAlert$.subscribe((alert) => this.deliver(alert));
  }

  private deliver(alert: OperatorAlert): void {
    const p = this.prefs;
    const quietHours = p ? this.isQuietHours(p) : false;

    // Toast
    if (!p || p.toast_enabled) {
      this.toastSvc.showForAlert(alert, p?.toast_min_severity ?? 'warning');
    }

    // Desktop
    if (p?.desktop_enabled !== false) {
      this.desktopSvc.showForAlert(alert, p?.min_desktop_severity ?? 'warning', quietHours);
    }

    // Sound
    if (p?.sound_enabled !== false) {
      this.audioSvc.playForAlert(alert, p?.min_sound_severity ?? 'error', quietHours);
    }
  }

  private isQuietHours(p: NotificationPreferences): boolean {
    if (!p.quiet_hours_enabled) return false;
    try {
      const now = new Date();
      const [startH, startM] = p.quiet_hours_start.split(':').map(Number);
      const [endH, endM] = p.quiet_hours_end.split(':').map(Number);
      const nowMins = now.getHours() * 60 + now.getMinutes();
      const startMins = startH * 60 + startM;
      const endMins = endH * 60 + endM;

      if (startMins <= endMins) {
        return nowMins >= startMins && nowMins < endMins;
      }
      // Overnight window (e.g. 22:00 – 07:00)
      return nowMins >= startMins || nowMins < endMins;
    } catch {
      return false;
    }
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
