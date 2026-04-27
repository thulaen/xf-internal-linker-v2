import { Injectable, OnDestroy, inject, NgZone } from '@angular/core';
import { BehaviorSubject, Observable, Subject } from 'rxjs';
import { filter } from 'rxjs/operators';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import {
  ConnectionStatus,
  IncomingFrame,
  OutgoingFrame,
  TopicUpdate,
} from './realtime.types';

/**
 * RealtimeService — singleton manager for the generic /ws/realtime/ socket.
 *
 * Responsibilities
 * ----------------
 * - Maintain ONE WebSocket per tab regardless of how many components
 *   subscribe to how many topics.
 * - Expose `subscribeTopic(topic)` returning an Observable<TopicUpdate> using
 *   refCount semantics — the first subscriber causes a server-side
 *   `subscribe` frame, the last unsubscribe causes an `unsubscribe` frame.
 * - Auto-reconnect with exponential backoff (1s → 30s cap) and re-subscribe
 *   all active topics when the socket recovers.
 * - Expose `connectionStatus$` for the WS status dot.
 *
 * Topic owners (every backend producer broadcasts via apps.realtime.services.broadcast):
 * - `system.pulse` — crawler heartbeat (PulseService)
 * - `notifications.alerts` — operator alerts (NotificationService)
 * - presence/cursor/lock/typing.* — collaboration namespaces
 * - diagnostics, settings.runtime, crawler.sessions, etc.
 *
 * Job-progress sockets (`/ws/jobs/<id>/`) are intentionally separate: they
 * are short-lived per-job streams, not a multiplexed topic bus, and stay
 * open only while a single job is running.
 *
 * What this service deliberately does NOT do
 * ------------------------------------------
 * - Parse topic payload shapes. Consumers cast the generic payload.
 */
@Injectable({ providedIn: 'root' })
export class RealtimeService implements OnDestroy {
  private readonly zone = inject(NgZone);
  private readonly auth = inject(AuthService);

  // ── Connection state ─────────────────────────────────────────────
  private socket: WebSocket | null = null;
  private destroyed = false;
  /** Auth gate. Server rejects the socket with 403 when false, so we
   *  simply don't dial until a valid session exists. */
  private loggedIn = false;

  /** Exponential-backoff state. Reset on successful open. */
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  /** After this many consecutive failed handshakes we stop dialling so
   *  a persistently broken socket doesn't burn the backend with 403s. */
  private readonly MAX_RETRIES = 6;
  /** Heartbeat ping so idle corporate proxies don't silently drop the socket. */
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  private readonly _status$ = new BehaviorSubject<ConnectionStatus>('offline');
  readonly connectionStatus$: Observable<ConnectionStatus> =
    this._status$.asObservable();

  // ── Topic multiplexing ───────────────────────────────────────────

  /** All frames from the socket, fan-out to per-topic subjects. */
  private readonly incoming$ = new Subject<TopicUpdate>();

  /** Ref-count per topic so we know when to fire subscribe / unsubscribe. */
  private readonly refCounts = new Map<string, number>();

  constructor() {
    // Lazy connect — the socket opens on the first subscribe() call.
    // Doing it in the constructor would open a socket even on pages that
    // never use realtime (e.g. /login).
    //
    // Auth awareness: even with lazy connect, pre-login components (e.g.
    // presence heartbeat, status pill) call subscribeTopic() before auth
    // resolves, which dialled the socket and ate a 403 with a reconnect
    // loop. Track loggedIn state so ensureSocketOpen() can defer the
    // handshake until there's a real session, and tear down on logout.
    this.auth.isLoggedIn$.subscribe((loggedIn) => {
      this.loggedIn = loggedIn;
      if (loggedIn) {
        // Fresh session → allow the retry budget to start over.
        this.reconnectAttempt = 0;
        if (this.refCounts.size > 0) {
          this.ensureSocketOpen();
        }
      } else {
        this.teardownOnLogout();
      }
    });
  }

  private teardownOnLogout(): void {
    this.clearReconnectTimer();
    this.clearPingTimer();
    if (this.socket) {
      try {
        this.socket.close();
      } catch {
        // ignore
      }
      this.socket = null;
    }
    this._status$.next('offline');
  }

  // ── Public API ───────────────────────────────────────────────────

  /**
   * Subscribe to a topic. Returns an Observable that emits every incoming
   * `topic.update` message whose `topic` field equals the requested name.
   *
   * Usage:
   *   inject(RealtimeService)
   *     .subscribe<MyPayload>('diagnostics')
   *     .subscribe(update => handle(update.event, update.payload));
   *
   * Unsubscribing from the returned Observable is what drives the
   * server-side `unsubscribe` frame.
   */
  subscribeTopic<T = unknown>(topic: string): Observable<TopicUpdate<T>> {
    const normalised = topic.trim();
    if (!normalised) {
      throw new Error('[RealtimeService] topic must be a non-empty string');
    }

    // `incoming$` is a Subject — it already multicasts to every subscriber.
    // We return a thin Observable wrapper whose only side effects are
    // acquire/release on subscription boundaries, which is what drives the
    // server-side subscribe/unsubscribe frames.
    return new Observable<TopicUpdate<T>>((subscriber) => {
      this.acquireTopic(normalised);
      const inner = this.incoming$
        .pipe(filter((u) => u.topic === normalised))
        .subscribe({
          next: (update) => subscriber.next(update as TopicUpdate<T>),
          error: (err) => subscriber.error(err),
          complete: () => subscriber.complete(),
        });
      return () => {
        inner.unsubscribe();
        this.releaseTopic(normalised);
      };
    });
  }

  /**
   * Phase RC / Gaps 139-142 — publish a payload to a collaboration
   * topic. The backend fans the event out to every other subscriber
   * (and to the publisher's other tabs) but enforces that only
   * `presence.*`, `cursor.*`, `lock.*`, and `typing.*` topics accept
   * client publishes — anything else returns an error frame.
   *
   * Fire-and-forget: the WebSocket is queued / opened on demand if
   * not currently connected. Frames sent while disconnected are
   * dropped (deliberately — stale presence data shouldn't be
   * resurrected after a long offline window).
   */
  publish(topic: string, event: string, payload: Record<string, unknown> = {}): void {
    const t = topic.trim();
    const e = event.trim();
    if (!t || !e) return;
    this.ensureSocketOpen();
    this.send({ action: 'publish', topic: t, event: e, payload });
  }

  /** Force an immediate reconnect attempt. Safe to call anytime. */
  reconnectNow(): void {
    if (this.socket) {
      try {
        this.socket.close();
      } catch {
        // ignore
      }
      this.socket = null;
    }
    this.clearReconnectTimer();
    this.openSocket();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.clearReconnectTimer();
    this.clearPingTimer();
    if (this.socket) {
      try {
        this.socket.close();
      } catch {
        // ignore
      }
      this.socket = null;
    }
    this._status$.next('offline');
  }

  // ── Ref-counting helpers ─────────────────────────────────────────

  private acquireTopic(topic: string): void {
    const next = (this.refCounts.get(topic) ?? 0) + 1;
    this.refCounts.set(topic, next);
    if (next === 1) {
      this.ensureSocketOpen();
      this.send({ action: 'subscribe', topics: [topic] });
    }
  }

  private releaseTopic(topic: string): void {
    const current = this.refCounts.get(topic) ?? 0;
    if (current <= 1) {
      this.refCounts.delete(topic);
      this.send({ action: 'unsubscribe', topics: [topic] });
    } else {
      this.refCounts.set(topic, current - 1);
    }
  }

  private activeTopics(): string[] {
    return Array.from(this.refCounts.keys());
  }

  // ── Socket management ────────────────────────────────────────────

  private ensureSocketOpen(): void {
    if (this.destroyed) return;
    // Don't dial a socket the server will reject with 403. Pre-login
    // subscribers still enqueue their topic ref-count; when isLoggedIn$
    // flips to true the constructor subscription calls ensureSocketOpen
    // again and catches them up.
    if (!this.loggedIn) return;
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
      // Either CONNECTING (0) or OPEN (1) — nothing to do.
      return;
    }
    this.openSocket();
  }

  private openSocket(): void {
    if (this.destroyed) return;
    const url = this.buildSocketUrl('/realtime/');

    // Run outside Angular so mouse-idle browsers don't pay change-detection
    // tax for every incoming frame. Consumers that need zone-awareness can
    // wrap their subscribe callback in NgZone.run themselves.
    this.zone.runOutsideAngular(() => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        this.scheduleReconnect();
        return;
      }

      this._status$.next(this.reconnectAttempt === 0 ? 'offline' : 'reconnecting');

      ws.onopen = () => {
        this.reconnectAttempt = 0;
        this._status$.next('connected');
        this.startPingTimer();
        // Re-send subscribes for every topic that had refs before the break.
        const topics = this.activeTopics();
        if (topics.length > 0) {
          this.sendFrame(ws, { action: 'subscribe', topics });
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        this.handleMessage(event.data);
      };

      ws.onerror = () => {
        // Let onclose schedule the retry. onerror fires without enough info
        // to distinguish transient blips from policy rejections.
        try {
          ws.close();
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        this.clearPingTimer();
        this.socket = null;
        // Only retry while the session is still valid. On logout we
        // deliberately close() and `loggedIn` is false — don't hammer
        // the server with 403s.
        if (!this.destroyed && this.loggedIn && this.refCounts.size > 0) {
          this._status$.next('reconnecting');
          this.scheduleReconnect();
        } else {
          this._status$.next('offline');
        }
      };

      this.socket = ws;
    });
  }

  private buildSocketUrl(path: string): string {
    const baseUrl = `${environment.wsBaseUrl}${path}`;
    const token = this.auth.getToken();
    if (!token) {
      return baseUrl;
    }
    return `${baseUrl}?token=${encodeURIComponent(token)}`;
  }

  private scheduleReconnect(): void {
    if (this.destroyed) return;
    // Give up after MAX_RETRIES consecutive failures — the next login
    // resets the counter, so the user can recover by signing out and in.
    if (this.reconnectAttempt >= this.MAX_RETRIES) {
      this._status$.next('offline');
      return;
    }
    this.clearReconnectTimer();
    // Exponential 1s, 2s, 4s, 8s, 16s, 30s cap. Small jitter so N tabs
    // don't stampede the server after a network blip.
    const base = Math.min(1000 * 2 ** this.reconnectAttempt, 30_000);
    const jitter = Math.floor(Math.random() * 500);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, base + jitter);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private startPingTimer(): void {
    this.clearPingTimer();
    // 25s is under the 30s default proxy idle timeout most setups use.
    // Skip the ping when the tab is hidden — the browser itself will
    // throttle or tear down the socket, and there is no operator
    // waiting for an update. See docs/PERFORMANCE.md §13.
    this.pingTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      this.send({ action: 'ping' });
    }, 25_000);
  }

  private clearPingTimer(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  // ── Wire protocol ────────────────────────────────────────────────

  private send(frame: OutgoingFrame): void {
    const ws = this.socket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Frames sent while the socket is connecting are dropped intentionally;
      // the onopen handler re-subscribes all active topics, so no state is lost.
      return;
    }
    this.sendFrame(ws, frame);
  }

  private sendFrame(ws: WebSocket, frame: OutgoingFrame): void {
    try {
      ws.send(JSON.stringify(frame));
    } catch {
      // Serialization failures shouldn't happen (frames are simple objects);
      // if they do, the connection is already in a bad state and onclose
      // will trigger reconnect.
    }
  }

  private handleMessage(raw: unknown): void {
    let parsed: IncomingFrame | null = null;
    if (typeof raw === 'string') {
      try {
        parsed = JSON.parse(raw) as IncomingFrame;
      } catch {
        parsed = null;
      }
    }
    if (!parsed || typeof parsed !== 'object' || !('type' in parsed)) {
      return;
    }

    if (parsed.type === 'topic.update') {
      // Re-enter Angular's zone so template bindings using async pipe
      // update without manual change detection calls.
      this.zone.run(() => {
        this.incoming$.next({
          topic: parsed!.topic as string,
          event: (parsed as { event: string }).event,
          payload: (parsed as { payload: unknown }).payload,
          receivedAt: Date.now(),
        });
      });
      return;
    }

    // Other frames (acks, pong, error) are no-ops for consumers today —
    // they exist for debugging and future features (Gap 38 detail tooltip).
  }
}
