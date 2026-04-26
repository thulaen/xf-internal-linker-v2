/**
 * ScheduledUpdatesService — REST + WebSocket client for the backend's
 * Scheduled Updates orchestrator (PR-B).
 *
 * REST: one method per endpoint defined in apps.scheduled_updates.urls.
 * WebSocket: subscribes to the `scheduled_updates` topic on the shared
 * /ws/realtime/ socket so the UI reflects live runner progress, state
 * changes, and alerts without polling.
 */

import { inject, Injectable, OnDestroy } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { BehaviorSubject, Observable, Subscription, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { RealtimeService } from '../core/services/realtime.service';
import { TopicUpdate } from '../core/services/realtime.types';

// ────────────────────────────────────────────────────────────────────
// Domain types — match backend serializers 1:1.
// ────────────────────────────────────────────────────────────────────

export type JobState =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'missed';

export type JobPriority = 'critical' | 'high' | 'medium' | 'low';

export type AlertType = 'missed' | 'failed' | 'stalled';

export interface ScheduledJob {
  id: number;
  key: string;
  display_name: string;
  priority: JobPriority;
  state: JobState;
  progress_pct: number;
  current_message: string;
  started_at: string | null;
  finished_at: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  scheduled_for: string | null;
  cadence_seconds: number;
  duration_estimate_sec: number;
  pause_token: boolean;
  log_tail: string;
  created_at: string;
  updated_at: string;
}

export interface JobAlert {
  id: number;
  job_key: string;
  alert_type: AlertType;
  calendar_date: string;
  message: string;
  first_raised_at: string | null;
  last_seen_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WindowStatus {
  is_within_window: boolean;
  seconds_remaining_in_window: number;
  seconds_until_window_opens: number;
}

export interface JobProgressFrame {
  key: string;
  progress_pct: number;
  current_message: string;
}

// Event names the backend fires on the `scheduled_updates` topic.
export type ScheduledUpdatesEvent =
  | 'job.state_change'
  | 'job.progress'
  | 'alert.raised'
  | 'alert.resolved'
  | 'alert.acknowledged';

// ────────────────────────────────────────────────────────────────────
// Service
// ────────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class ScheduledUpdatesService implements OnDestroy {
  private http = inject(HttpClient);
  private realtime = inject(RealtimeService);

  private readonly apiBase = '/api/scheduled-updates';
  private readonly topic = 'scheduled_updates';

  // Hot streams so every subscriber gets the latest snapshot without
  // re-fetching. Components that only care about live events can
  // subscribe directly; components that want a snapshot + live updates
  // call one of the refresh* methods and then subscribe.
  private readonly jobsSubject = new BehaviorSubject<ScheduledJob[]>([]);
  private readonly alertsSubject = new BehaviorSubject<JobAlert[]>([]);
  private readonly windowSubject = new BehaviorSubject<WindowStatus | null>(null);
  private readonly liveProgressSubject = new BehaviorSubject<JobProgressFrame | null>(null);

  readonly jobs$: Observable<ScheduledJob[]> = this.jobsSubject.asObservable();
  readonly alerts$: Observable<JobAlert[]> = this.alertsSubject.asObservable();
  readonly windowStatus$: Observable<WindowStatus | null> = this.windowSubject.asObservable();
  readonly liveProgress$: Observable<JobProgressFrame | null> =
    this.liveProgressSubject.asObservable();

  private wsSubscription?: Subscription;

  // ── REST ─────────────────────────────────────────────────────────

  listJobs(): Observable<ScheduledJob[]> {
    return this.http
      .get<PaginatedOrList<ScheduledJob>>(`${this.apiBase}/jobs/`)
      .pipe(map(unwrapList));
  }

  refreshJobs(): Observable<ScheduledJob[]> {
    const o = this.listJobs();
    o.subscribe({ next: (jobs) => this.jobsSubject.next(jobs) });
    return o;
  }

  getJob(id: number): Observable<ScheduledJob> {
    return this.http
      .get<ScheduledJob>(`${this.apiBase}/jobs/${id}/`)
      .pipe(catchError((err) => throwError(() => err)));
  }

  pauseJob(id: number): Observable<ScheduledJob> {
    return this.http
      .post<ScheduledJob>(`${this.apiBase}/jobs/${id}/pause/`, {})
      .pipe(catchError((err) => throwError(() => err)));
  }

  resumeJob(id: number): Observable<ScheduledJob> {
    return this.http
      .post<ScheduledJob>(`${this.apiBase}/jobs/${id}/resume/`, {})
      .pipe(catchError((err) => throwError(() => err)));
  }

  cancelJob(id: number): Observable<ScheduledJob> {
    return this.http
      .post<ScheduledJob>(`${this.apiBase}/jobs/${id}/cancel/`, {})
      .pipe(catchError((err) => throwError(() => err)));
  }

  runNow(id: number): Observable<ScheduledJob> {
    return this.http
      .post<ScheduledJob>(`${this.apiBase}/jobs/${id}/run-now/`, {})
      .pipe(catchError((err) => throwError(() => err)));
  }

  listAlerts(include: 'active' | 'all' | 'resolved' = 'active'): Observable<JobAlert[]> {
    const params = new HttpParams().set('include', include);
    return this.http
      .get<PaginatedOrList<JobAlert>>(`${this.apiBase}/alerts/`, { params })
      .pipe(map(unwrapList));
  }

  refreshAlerts(include: 'active' | 'all' | 'resolved' = 'active'): Observable<JobAlert[]> {
    const o = this.listAlerts(include);
    o.subscribe({ next: (alerts) => this.alertsSubject.next(alerts) });
    return o;
  }

  acknowledgeAlert(id: number): Observable<JobAlert> {
    return this.http
      .post<JobAlert>(`${this.apiBase}/alerts/${id}/acknowledge/`, {})
      .pipe(catchError((err) => throwError(() => err)));
  }

  getWindowStatus(): Observable<WindowStatus> {
    return this.http
      .get<WindowStatus>(`${this.apiBase}/window/`)
      .pipe(catchError((err) => throwError(() => err)));
  }

  refreshWindowStatus(): Observable<WindowStatus> {
    const o = this.getWindowStatus();
    o.subscribe({ next: (status) => this.windowSubject.next(status) });
    return o;
  }

  // ── WebSocket wiring ─────────────────────────────────────────────

  /**
   * Subscribe to the `scheduled_updates` topic and fold each event into
   * the appropriate BehaviorSubject so the UI updates without a refetch.
   * Safe to call multiple times — internally idempotent.
   */
  startRealtimeStream(): void {
    if (this.wsSubscription) {
      return;
    }
    this.wsSubscription = this.realtime
      .subscribeTopic<unknown>(this.topic)
      .subscribe({
        next: (update: TopicUpdate<unknown>) => this.handleEnvelope(update),
        error: (err) => console.error('[scheduled-updates] WS error', err),
      });
  }

  stopRealtimeStream(): void {
    this.wsSubscription?.unsubscribe();
    this.wsSubscription = undefined;
  }

  private handleEnvelope(envelope: TopicUpdate<unknown>): void {
    switch (envelope.event) {
      case 'job.state_change': {
        const payload = envelope.payload as ScheduledJob & { key: string };
        this.upsertJobByKey(payload);
        break;
      }
      case 'job.progress': {
        this.liveProgressSubject.next(envelope.payload as JobProgressFrame);
        break;
      }
      case 'alert.raised':
      case 'alert.acknowledged': {
        const alert = envelope.payload as JobAlert;
        this.upsertAlertById(alert);
        break;
      }
      case 'alert.resolved': {
        // Coarse — we refetch so the list reflects the server's truth
        // (which rows got resolved isn't in the payload).
        this.refreshAlerts().subscribe();
        break;
      }
    }
  }

  private upsertJobByKey(incoming: ScheduledJob & { key: string }): void {
    const current = this.jobsSubject.value;
    const idx = current.findIndex((j) => j.key === incoming.key);
    let next: ScheduledJob[];
    if (idx >= 0) {
      next = [...current];
      next[idx] = { ...current[idx], ...incoming };
    } else {
      next = [...current, incoming as ScheduledJob];
    }
    this.jobsSubject.next(next);
  }

  private upsertAlertById(incoming: JobAlert): void {
    const current = this.alertsSubject.value;
    const idx = current.findIndex((a) => a.id === incoming.id);
    let next: JobAlert[];
    if (idx >= 0) {
      next = [...current];
      next[idx] = incoming;
    } else {
      next = [incoming, ...current];
    }
    this.alertsSubject.next(next);
  }

  ngOnDestroy(): void {
    this.stopRealtimeStream();
  }
}

// DRF may page-wrap list endpoints. Accept either shape.
type PaginatedOrList<T> = T[] | { results: T[] };

function unwrapList<T>(payload: PaginatedOrList<T>): T[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  return payload.results ?? [];
}
