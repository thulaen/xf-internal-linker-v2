/**
 * PulseService — connects to the system heartbeat WebSocket and provides
 * real-time liveness data for the toolbar pulse indicator and Dashboard
 * activity feed.
 *
 * Tier 1: Toolbar pulse (green/yellow/red dot, task count, last beat).
 * Tier 2: Dashboard activity feed (last 50 system events).
 * Tier 3: Page context headers (per-page freshness — handled by each page).
 *
 * Auth-aware: the WebSocket and the stale-check timer only run while the
 * user is signed in. This prevents 403 spam on the login screen and stops
 * the 5-second reconnect loop from triggering Angular change detection
 * while unauthenticated.
 *
 * Zone-safe: all timers run outside Angular's zone so they don't cause
 * global change detection on every tick. Subjects re-enter the zone on emit.
 */

import { Injectable, NgZone, OnDestroy, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, Subscription } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';

export interface PulseState {
  ok: boolean;
  status: 'live' | 'degraded' | 'down' | 'unknown';
  lastBeatAt: number; // epoch seconds
  checks: Record<string, { ok: boolean; ms?: number; workers?: number; tasks?: number; error?: string }>;
  taskCount: number;
}

export interface SystemEvent {
  event_id: string;
  severity: 'info' | 'success' | 'warning' | 'error';
  source: string;
  title: string;
  detail: string;
  metadata: Record<string, any>;
  timestamp: string;
}

@Injectable({ providedIn: 'root' })
export class PulseService implements OnDestroy {
  private http = inject(HttpClient);
  private zone = inject(NgZone);
  private auth = inject(AuthService);

  private _pulse$ = new BehaviorSubject<PulseState>({
    ok: false,
    status: 'unknown',
    lastBeatAt: 0,
    checks: {},
    taskCount: 0,
  });
  readonly pulse$: Observable<PulseState> = this._pulse$.asObservable();

  private _events$ = new BehaviorSubject<SystemEvent[]>([]);
  readonly events$: Observable<SystemEvent[]> = this._events$.asObservable();

  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private staleTimer: ReturnType<typeof setInterval> | null = null;
  private destroyed = false;
  private loggedIn = false;
  private authSub: Subscription;

  constructor() {
    // Gate everything on auth state — no sockets or timers before login.
    this.authSub = this.auth.isLoggedIn$.subscribe((loggedIn) => {
      this.loggedIn = loggedIn;
      if (loggedIn) {
        this.stop(); // Clear any existing leaked sockets/timers
        this.start();
      } else {
        this.stop();
      }
    });
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.authSub.unsubscribe();
    this.stop();
  }

  /** Fetch recent system events from the REST API. */
  loadRecentEvents(): void {
    this.http
      .get<SystemEvent[]>(`${environment.apiBaseUrl}/crawler/events/`)
      .subscribe({
        next: (events) => this.zone.run(() => this._events$.next(events)),
        error: () => console.warn('[PulseService] Failed to load recent events'),
      });
  }

  private start(): void {
    this.loadRecentEvents();
    this.connectWebSocket();
    // Run the stale check outside Angular's zone so it doesn't trigger
    // global change detection every 30 seconds.
    this.zone.runOutsideAngular(() => {
      this.staleTimer = setInterval(() => this.checkStale(), 30_000);
    });
  }

  private stop(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.staleTimer) {
      clearInterval(this.staleTimer);
      this.staleTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    // Reset to unknown state on logout so stale data isn't shown on next login.
    this.zone.run(() =>
      this._pulse$.next({ ok: false, status: 'unknown', lastBeatAt: 0, checks: {}, taskCount: 0 })
    );
  }

  private connectWebSocket(): void {
    if (this.destroyed || !this.loggedIn) return;
    // Open outside Angular's zone so WebSocket events don't trigger
    // change detection globally. Individual handlers re-enter the zone
    // only when they emit to subjects.
    this.zone.runOutsideAngular(() => {
      try {
        const baseUrl = `${environment.wsBaseUrl}/notifications/`;
        const token = this.auth.getToken();
        const url = token ? `${baseUrl}?token=${encodeURIComponent(token)}` : baseUrl;
        this.ws = new WebSocket(url);

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data as string);
            if (data.type === 'pulse.heartbeat') {
              this.handleHeartbeat(data);
            }
          } catch {
            // Ignore malformed messages.
          }
        };

        this.ws.onclose = () => {
          if (this.destroyed || !this.loggedIn) return;
          this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 5_000);
        };

        this.ws.onerror = () => {
          // onclose fires after onerror and schedules the reconnect.
        };
      } catch {
        if (this.destroyed || !this.loggedIn) return;
        this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 5_000);
      }
    });
  }

  private lastEventsLoadAt = 0;
  private readonly EVENTS_MIN_INTERVAL_MS = 25_000;

  private handleHeartbeat(data: any): void {
    const taskCount = data.checks?.celery?.tasks ?? 0;
    const pulse: PulseState = {
      ok: data.ok,
      status: data.ok ? 'live' : 'degraded',
      lastBeatAt: data.timestamp ?? Date.now() / 1000,
      checks: data.checks ?? {},
      taskCount,
    };
    // Re-enter Angular's zone so async-pipe subscribers update correctly.
    this.zone.run(() => {
      this._pulse$.next(pulse);
      // Throttle the events refresh to at most once per 25s — the heartbeat
      // fires every ~30s but can arrive more frequently during reconnects,
      // which previously caused a burst of GET /api/crawler/events/ calls.
      const now = Date.now();
      if (now - this.lastEventsLoadAt >= this.EVENTS_MIN_INTERVAL_MS) {
        this.lastEventsLoadAt = now;
        this.loadRecentEvents();
      }
    });
  }

  private checkStale(): void {
    const current = this._pulse$.value;
    if (current.lastBeatAt === 0) return;
    const ageSec = Date.now() / 1000 - current.lastBeatAt;

    if (ageSec > 180) {
      this.zone.run(() => this._pulse$.next({ ...current, status: 'down' }));
    } else if (ageSec > 90) {
      this.zone.run(() => this._pulse$.next({ ...current, status: 'degraded' }));
    }
  }
}
