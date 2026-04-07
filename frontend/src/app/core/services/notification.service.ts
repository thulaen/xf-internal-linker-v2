/**
 * NotificationService — REST + WebSocket client for OperatorAlerts.
 *
 * Responsibilities:
 *  - Poll /api/notifications/alerts/summary/ on startup for the initial badge count.
 *  - Open ws/notifications/ and keep it alive; push new alerts into unreadCount$.
 *  - Expose observables that the shell and notification center subscribe to.
 *  - Provide action helpers (read, acknowledge, resolve, acknowledgeAll).
 */

import { Injectable, OnDestroy, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import {
  BehaviorSubject,
  Observable,
  Subject,
  catchError,
  of,
  tap,
} from 'rxjs';
import { environment } from '../../../environments/environment';

export interface OperatorAlert {
  id: number;
  alert_id: string;
  event_type: string;
  source_area: string;
  severity: 'info' | 'success' | 'warning' | 'error' | 'urgent';
  status: 'unread' | 'read' | 'acknowledged' | 'resolved';
  title: string;
  message: string;
  dedupe_key: string;
  occurrence_count: number;
  related_object_type: string;
  related_object_id: string;
  related_route: string;
  payload: Record<string, unknown>;
  error_log_id: number | null;
  first_seen_at: string;
  last_seen_at: string;
  read_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertSummary {
  total_unread: number;
  by_severity: Record<string, number>;
  latest_at: string | null;
}

export interface NotificationPreferences {
  desktop_enabled: boolean;
  sound_enabled: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  min_desktop_severity: string;
  min_sound_severity: string;
  enable_job_completed: boolean;
  enable_job_failed: boolean;
  enable_job_stalled: boolean;
  enable_model_status: boolean;
  enable_gsc_spikes: boolean;
  toast_enabled: boolean;
  toast_min_severity: string;
  duplicate_cooldown_seconds: number;
  job_stalled_default_minutes: number;
  gsc_spike_min_impressions_delta: number;
  gsc_spike_min_clicks_delta: number;
  gsc_spike_min_relative_lift: number;
}

@Injectable({ providedIn: 'root' })
export class NotificationService implements OnDestroy {
  private http = inject(HttpClient);

  private _unreadCount$ = new BehaviorSubject<number>(0);
  private _newAlert$ = new Subject<OperatorAlert>();

  /** Total unread alert count — drives the toolbar badge. */
  readonly unreadCount$: Observable<number> = this._unreadCount$.asObservable();

  /** Fires whenever a new alert arrives via WebSocket — used by delivery services. */
  readonly newAlert$: Observable<OperatorAlert> = this._newAlert$.asObservable();

  private ws: WebSocket | null = null;
  private destroyed = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    this.loadSummary();
    this.connectWebSocket();
  }

  // ── REST helpers ──────────────────────────────────────────────────

  loadAlerts(params: Record<string, string> = {}): Observable<OperatorAlert[]> {
    const query = new URLSearchParams(params).toString();
    const url = `/api/notifications/alerts/${query ? '?' + query : ''}`;
    return this.http.get<OperatorAlert[]>(url).pipe(
      catchError(() => of([] as OperatorAlert[])),
    );
  }

  loadSummary(): void {
    this.http
      .get<AlertSummary>('/api/notifications/alerts/summary/')
      .pipe(catchError(() => of(null)))
      .subscribe((s) => {
        if (s) this._unreadCount$.next(s.total_unread);
      });
  }

  markRead(alertId: string): Observable<OperatorAlert> {
    return this.http
      .post<OperatorAlert>(`/api/notifications/alerts/${alertId}/read/`, {})
      .pipe(tap(() => this.loadSummary()));
  }

  acknowledge(alertId: string): Observable<OperatorAlert> {
    return this.http
      .post<OperatorAlert>(`/api/notifications/alerts/${alertId}/acknowledge/`, {})
      .pipe(tap(() => this.loadSummary()));
  }

  resolve(alertId: string): Observable<OperatorAlert> {
    return this.http
      .post<OperatorAlert>(`/api/notifications/alerts/${alertId}/resolve/`, {})
      .pipe(tap(() => this.loadSummary()));
  }

  acknowledgeAll(): Observable<{ acknowledged: number }> {
    return this.http
      .post<{ acknowledged: number }>('/api/notifications/alerts/acknowledge-all/', {})
      .pipe(tap(() => this._unreadCount$.next(0)));
  }

  loadPreferences(): Observable<NotificationPreferences> {
    return this.http.get<NotificationPreferences>('/api/settings/notifications/');
  }

  savePreferences(prefs: Partial<NotificationPreferences>): Observable<NotificationPreferences> {
    return this.http.put<NotificationPreferences>('/api/settings/notifications/', prefs);
  }

  sendTestNotification(severity = 'warning'): Observable<OperatorAlert> {
    return this.http
      .post<OperatorAlert>('/api/notifications/test/', { severity })
      .pipe(tap(() => this.loadSummary()));
  }

  // ── WebSocket ─────────────────────────────────────────────────────

  private connectWebSocket(): void {
    if (this.destroyed) return;
    const url = `${environment.wsBaseUrl}/notifications/`;
    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        // Connected — clear any pending reconnect timer
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          if (data.type === 'notification.alert') {
            this._unreadCount$.next(this._unreadCount$.value + 1);
            this._newAlert$.next(data as OperatorAlert);
          }
        } catch {
          // Malformed message — ignore
        }
      };

      this.ws.onclose = () => {
        if (!this.destroyed) {
          this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
        }
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      if (!this.destroyed) {
        this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
      }
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      // Null out onclose before calling close() so the async close event
      // cannot schedule a reconnect after the service has been destroyed.
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
