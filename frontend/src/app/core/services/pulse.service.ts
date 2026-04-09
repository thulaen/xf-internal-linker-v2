/**
 * PulseService — connects to the system heartbeat WebSocket and provides
 * real-time liveness data for the toolbar pulse indicator and Dashboard
 * activity feed.
 *
 * Tier 1: Toolbar pulse (green/yellow/red dot, task count, last beat).
 * Tier 2: Dashboard activity feed (last 50 system events).
 * Tier 3: Page context headers (per-page freshness — handled by each page).
 */

import { Injectable, OnDestroy, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

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

  constructor() {
    this.connectWebSocket();
    this.loadRecentEvents();

    // Check for stale heartbeat every 30 seconds.
    this.staleTimer = setInterval(() => this.checkStale(), 30_000);
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.staleTimer) clearInterval(this.staleTimer);
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }
  }

  /** Fetch recent system events from the REST API. */
  loadRecentEvents(): void {
    this.http
      .get<SystemEvent[]>(`${environment.apiBaseUrl}/crawler/events/`)
      .subscribe({
        next: (events) => this._events$.next(events),
        error: () => {},
      });
  }

  private connectWebSocket(): void {
    if (this.destroyed) return;
    try {
      const url = `${environment.wsBaseUrl}/notifications/`;
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
        if (!this.destroyed) {
          this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 5_000);
        }
      };

      this.ws.onerror = () => {
        // onclose will fire after onerror, triggering reconnect.
      };
    } catch {
      if (!this.destroyed) {
        this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 5_000);
      }
    }
  }

  private handleHeartbeat(data: any): void {
    const taskCount = data.checks?.celery?.tasks ?? 0;
    const pulse: PulseState = {
      ok: data.ok,
      status: data.ok ? 'live' : 'degraded',
      lastBeatAt: data.timestamp ?? Date.now() / 1000,
      checks: data.checks ?? {},
      taskCount,
    };
    this._pulse$.next(pulse);

    // Also refresh the event feed.
    this.loadRecentEvents();
  }

  private checkStale(): void {
    const current = this._pulse$.value;
    if (current.lastBeatAt === 0) return;
    const ageSec = Date.now() / 1000 - current.lastBeatAt;

    if (ageSec > 180) {
      this._pulse$.next({ ...current, status: 'down' });
    } else if (ageSec > 90) {
      this._pulse$.next({ ...current, status: 'degraded' });
    }
  }
}
