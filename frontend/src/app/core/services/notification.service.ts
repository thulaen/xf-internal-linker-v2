/**
 * NotificationService — REST + realtime client for OperatorAlerts.
 *
 * Responsibilities:
 *  - Poll /api/notifications/alerts/summary/ on login for the initial badge count.
 *  - Subscribe to the `notifications.alerts` topic on the shared realtime
 *    socket; push new alerts into unreadCount$ and newAlert$.
 *  - Expose action helpers (read, acknowledge, resolve, acknowledgeAll).
 */

import { Injectable, OnDestroy, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import {
  BehaviorSubject,
  Observable,
  Subject,
  Subscription,
  catchError,
  map,
  of,
  tap,
} from 'rxjs';
import { AuthService } from './auth.service';
import { RealtimeService } from './realtime.service';

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
  suppressed_until: string | null;
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

/**
 * Server response shape for `GET /api/notifications/alerts/`.
 * Mirrors DRF's PageNumberPagination envelope so the alerts page can
 * paginate without needing a custom server contract. Same shape is
 * already used by /api/suggestions/ etc.
 */
export interface PaginatedAlerts {
  count: number;
  next: string | null;
  previous: string | null;
  results: OperatorAlert[];
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
  private auth = inject(AuthService);
  private realtime = inject(RealtimeService);

  private _unreadCount$ = new BehaviorSubject<number>(0);
  private _newAlert$ = new Subject<OperatorAlert>();
  private _resolved$ = new Subject<{ dedupe_key: string; resolved_at: string }>();

  /** Total unread alert count — drives the toolbar badge. */
  readonly unreadCount$: Observable<number> = this._unreadCount$.asObservable();

  /** Fires whenever a new alert arrives via the realtime topic. */
  readonly newAlert$: Observable<OperatorAlert> = this._newAlert$.asObservable();

  /** Fires whenever the backend resolves an alert. */
  readonly resolved$: Observable<{ dedupe_key: string; resolved_at: string }> =
    this._resolved$.asObservable();

  private destroyed = false;
  private topicSub: Subscription | null = null;
  private authSub: Subscription;

  constructor() {
    // Only talk to authenticated endpoints once the user is signed in.
    // Realtime delivery is multiplexed onto the shared /ws/realtime/ socket
    // via RealtimeService, so this service no longer opens its own.
    this.authSub = this.auth.isLoggedIn$.subscribe((loggedIn) => {
      if (loggedIn) {
        this.loadSummary();
        this.subscribeRealtime();
      } else {
        this.unsubscribeRealtime();
        this._unreadCount$.next(0);
      }
    });
  }

  // ── REST helpers ──────────────────────────────────────────────────

  loadAlerts(params: Record<string, string> = {}): Observable<PaginatedAlerts> {
    const query = new URLSearchParams(params).toString();
    const url = `/api/notifications/alerts/${query ? '?' + query : ''}`;
    return this.http.get<PaginatedAlerts>(url).pipe(
      catchError(() =>
        of({ count: 0, next: null, previous: null, results: [] } as PaginatedAlerts),
      ),
    );
  }

  getAlert(alertId: string): Observable<OperatorAlert | null> {
    return this.http
      .get<OperatorAlert>(`/api/notifications/alerts/${alertId}/`)
      .pipe(catchError(() => of(null)));
  }

  loadSummary(): void {
    this.http
      .get<AlertSummary>('/api/notifications/alerts/summary/')
      .pipe(
        catchError(() => {
          // Fallback: count unread alerts directly if summary endpoint fails.
          // The list endpoint is paginated, so we read `count` (the total
          // across all pages) rather than the length of the first page.
          return this.http
            .get<PaginatedAlerts>('/api/notifications/alerts/', { params: { status: 'unread' } })
            .pipe(
              map((paged) => ({ total_unread: paged.count, by_severity: {}, latest_at: null } as AlertSummary)),
              catchError(() => of(null)),
            );
        }),
      )
      .subscribe({
        next: (s) => {
          if (s) this._unreadCount$.next(s.total_unread);
        },
        error: () => console.error('[NotificationService] Failed to load alert summary (primary and fallback failed)'),
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
    return this.http
      .get<NotificationPreferences>('/api/settings/notifications/')
      .pipe(catchError(() => of({} as NotificationPreferences)));
  }

  savePreferences(prefs: Partial<NotificationPreferences>): Observable<NotificationPreferences> {
    return this.http
      .put<NotificationPreferences>('/api/settings/notifications/', prefs)
      .pipe(catchError(() => of({} as NotificationPreferences)));
  }

  sendTestNotification(severity = 'warning'): Observable<OperatorAlert> {
    return this.http
      .post<OperatorAlert>('/api/notifications/test/', { severity })
      .pipe(tap(() => this.loadSummary()));
  }

  // ── Realtime topic subscription ───────────────────────────────────

  private subscribeRealtime(): void {
    if (this.destroyed) return;
    this.unsubscribeRealtime();
    // The realtime topic delivers payloads typed `unknown` (the channel
    // layer is payload-agnostic). The wire shape is owned by the backend
    // producer (apps/notifications/services.py::_push_to_websocket and
    // resolve_operator_alert). Single-cast `as X` is sufficient — the
    // source is already `unknown`. Trust boundary documented; if a
    // future producer change drifts the shape, the cast lands on a
    // runtime field-access TypeError at the consumer, not a silent
    // type-laundering compile success.
    this.topicSub = this.realtime
      .subscribeTopic<unknown>('notifications.alerts')
      .subscribe((update) => {
        if (update.event === 'alert.created') {
          const alert = update.payload as OperatorAlert;
          this._unreadCount$.next(this._unreadCount$.value + 1);
          this._newAlert$.next(alert);
        } else if (update.event === 'alert.resolved') {
          const payload = update.payload as { dedupe_key: string; resolved_at: string };
          this._resolved$.next(payload);
          // Refresh the badge — resolved alerts shouldn't keep counting.
          this.loadSummary();
        }
      });
  }

  private unsubscribeRealtime(): void {
    if (this.topicSub) {
      this.topicSub.unsubscribe();
      this.topicSub = null;
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.authSub.unsubscribe();
    this.unsubscribeRealtime();
  }
}
