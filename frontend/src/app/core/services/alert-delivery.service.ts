/**
 * AlertDeliveryService — fans out new realtime alerts to toast, desktop, and sound.
 *
 * Started once from AppComponent. The auth gate prevents
 * `/api/settings/notifications/` from being hit on the login page (which
 * would surface as a "Server error" toast, since the endpoint requires auth).
 */

import { Injectable, OnDestroy, inject } from '@angular/core';
import { Subscription } from 'rxjs';
import { AudioCueService } from './audio-cue.service';
import { AuthService } from './auth.service';
import { DesktopNotificationService } from './desktop-notification.service';
import { NotificationPreferences, NotificationService, OperatorAlert } from './notification.service';
import { ToastService } from './toast.service';

@Injectable({ providedIn: 'root' })
export class AlertDeliveryService implements OnDestroy {
  private notifSvc = inject(NotificationService);
  private toastSvc = inject(ToastService);
  private desktopSvc = inject(DesktopNotificationService);
  private audioSvc = inject(AudioCueService);
  private auth = inject(AuthService);

  private prefs: NotificationPreferences | null = null;
  private alertSub: Subscription | null = null;
  private authSub: Subscription | null = null;

  /** Call once from AppComponent.ngOnInit(). */
  start(): void {
    this.authSub?.unsubscribe();
    this.authSub = this.auth.isLoggedIn$.subscribe((isLoggedIn) => {
      if (isLoggedIn) {
        this.notifSvc.loadPreferences().subscribe({
          next: (p) => {
            this.prefs = p;
          },
          error: () => {
            this.prefs = null;
          },
        });
        this.alertSub?.unsubscribe();
        this.alertSub = this.notifSvc.newAlert$.subscribe((alert) => this.deliver(alert));
      } else {
        this.alertSub?.unsubscribe();
        this.alertSub = null;
        this.prefs = null;
      }
    });
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
    this.alertSub?.unsubscribe();
    this.authSub?.unsubscribe();
  }
}
