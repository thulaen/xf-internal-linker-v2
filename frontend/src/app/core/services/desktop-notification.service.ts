/**
 * DesktopNotificationService — Browser Notification API wrapper.
 *
 * Rules:
 *  - Never request permission on page load — only when the user enables
 *    desktop notifications in settings or clicks the test button.
 *  - If permission is denied, store a local flag so the UI can show a hint.
 *  - Falls back silently when the Notification API is unavailable.
 */

import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { OperatorAlert } from './notification.service';

export type NotifPermission = 'default' | 'granted' | 'denied' | 'unsupported';

const SEVERITY_RANK: Record<string, number> = {
  info: 0,
  success: 1,
  warning: 2,
  error: 3,
  urgent: 4,
};

@Injectable({ providedIn: 'root' })
export class DesktopNotificationService {
  private _permission$ = new BehaviorSubject<NotifPermission>(this.currentPermission());

  /** Current browser permission state. */
  readonly permission$: Observable<NotifPermission> = this._permission$.asObservable();

  get permission(): NotifPermission {
    return this._permission$.value;
  }

  private currentPermission(): NotifPermission {
    if (!('Notification' in window)) return 'unsupported';
    return Notification.permission as NotifPermission;
  }

  /**
   * Ask for permission. Should only be called when the user explicitly
   * enables desktop notifications in the settings card.
   */
  async requestPermission(): Promise<NotifPermission> {
    if (!('Notification' in window)) {
      this._permission$.next('unsupported');
      return 'unsupported';
    }
    const result = await Notification.requestPermission();
    this._permission$.next(result as NotifPermission);
    return result as NotifPermission;
  }

  /**
   * Show a desktop notification for an alert if the severity meets the
   * threshold and permission is granted.
   */
  showForAlert(
    alert: OperatorAlert,
    minSeverity = 'warning',
    quietHoursActive = false,
  ): void {
    if (quietHoursActive) return;
    if (this._permission$.value !== 'granted') return;

    const alertRank = SEVERITY_RANK[alert.severity] ?? 0;
    const minRank = SEVERITY_RANK[minSeverity] ?? 2;
    if (alertRank < minRank) return;

    try {
      const n = new Notification(alert.title, {
        body: alert.message,
        icon: '/favicon.ico',
        tag: alert.dedupe_key, // prevents duplicate OS notifications for same alert
        silent: true, // sound is handled by AudioCueService
      });

      if (alert.related_route) {
        n.onclick = () => {
          window.focus();
          window.location.assign(alert.related_route);
          n.close();
        };
      }

      // Auto-close after 8 seconds
      setTimeout(() => n.close(), 8000);
    } catch {
      // Notification API can throw in some browsers — ignore
    }
  }
}
