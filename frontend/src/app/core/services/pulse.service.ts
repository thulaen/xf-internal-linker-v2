/**
 * PulseService — toolbar pulse indicator + Dashboard activity feed.
 *
 * Tier 1: Toolbar pulse (green/yellow/red dot, task count, last beat).
 * Tier 2: Dashboard activity feed (last 50 system events).
 * Tier 3: Page context headers (per-page freshness — handled by each page).
 *
 * Heartbeat delivery is shared with the rest of the app via
 * RealtimeService.subscribeTopic('system.pulse'). The topic publishes one
 * `heartbeat` event every ~30s from `apps.crawler.tasks.pulse_heartbeat`.
 *
 * Auth-aware: the topic subscription and the stale-check timer only run
 * while the user is signed in. Zone-safe: stale checks run outside Angular's
 * zone; subjects re-enter the zone on emit.
 */

import { Injectable, NgZone, OnDestroy, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, Subscription } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { RealtimeService } from './realtime.service';

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

interface HeartbeatPayload {
  ok?: boolean;
  checks?: Record<string, { ok: boolean; tasks?: number; workers?: number; ms?: number; error?: string }>;
  timestamp?: number;
}

@Injectable({ providedIn: 'root' })
export class PulseService implements OnDestroy {
  private http = inject(HttpClient);
  private zone = inject(NgZone);
  private auth = inject(AuthService);
  private realtime = inject(RealtimeService);

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

  private staleTimer: ReturnType<typeof setInterval> | null = null;
  private destroyed = false;
  private topicSub: Subscription | null = null;
  private authSub: Subscription;

  constructor() {
    // Gate everything on auth state — no topic subscription or timers before login.
    this.authSub = this.auth.isLoggedIn$.subscribe((loggedIn) => {
      if (loggedIn) {
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
    this.stop();
    if (this.destroyed) return;
    this.loadRecentEvents();
    // Subscribe via the shared realtime socket — RealtimeService handles
    // retry budget, jitter, ping keepalive, and visibility gating.
    this.topicSub = this.realtime
      .subscribeTopic<HeartbeatPayload>('system.pulse')
      .subscribe((update) => {
        if (update.event === 'heartbeat') {
          this.handleHeartbeat(update.payload);
        }
      });
    // Stale check runs outside Angular's zone so it doesn't trigger global
    // change detection every 30 seconds.
    this.zone.runOutsideAngular(() => {
      this.staleTimer = setInterval(() => this.checkStale(), 30_000);
    });
  }

  private stop(): void {
    if (this.staleTimer) {
      clearInterval(this.staleTimer);
      this.staleTimer = null;
    }
    if (this.topicSub) {
      this.topicSub.unsubscribe();
      this.topicSub = null;
    }
    // Reset to unknown state on logout so stale data isn't shown on next login.
    this.zone.run(() =>
      this._pulse$.next({ ok: false, status: 'unknown', lastBeatAt: 0, checks: {}, taskCount: 0 })
    );
  }

  private lastEventsLoadAt = 0;
  private readonly EVENTS_MIN_INTERVAL_MS = 25_000;

  private handleHeartbeat(data: HeartbeatPayload): void {
    const taskCount = data.checks?.['celery']?.tasks ?? 0;
    const pulse: PulseState = {
      ok: !!data.ok,
      status: data.ok ? 'live' : 'degraded',
      lastBeatAt: data.timestamp ?? Date.now() / 1000,
      checks: data.checks ?? {},
      taskCount,
    };
    // Re-enter Angular's zone so async-pipe subscribers update correctly.
    this.zone.run(() => {
      this._pulse$.next(pulse);
      // Throttle the events refresh to at most once per 25s — the heartbeat
      // fires every ~30s but can arrive more frequently during reconnects.
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
