import {
  DestroyRef,
  Injectable,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, interval } from 'rxjs';

import { AuthService } from './auth.service';
import { RealtimeService } from './realtime.service';

/**
 * Phase RC / Gap 139 — Real-time presence service.
 *
 * Heartbeats the current user's username + active route over the
 * realtime WebSocket every 15 seconds, on the `presence.app` topic.
 * Listens to the same topic and tracks every other user heard from
 * in the last 30 seconds.
 *
 * Why one global topic instead of per-route: routes change a lot
 * during a session, but membership of "who is in the app right now"
 * is a single answer. The presence record carries the route so the
 * indicator can highlight people on the same page as you.
 *
 * Idle timeout: presence rows older than 30 seconds drop out of the
 * `peers` snapshot. The browser's `online`/`offline` events also
 * pause heartbeats when the network is gone.
 */

const TOPIC = 'presence.app';
const HEARTBEAT_MS = 15_000;
const STALE_AFTER_MS = 30_000;

export interface PresencePeer {
  username: string;
  route: string;
  /** ms epoch of the last heartbeat we heard from this peer. */
  lastSeen: number;
  /** Stable connection id from the publisher envelope. */
  connectionId: string;
}

@Injectable({ providedIn: 'root' })
export class PresenceService {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);

  private currentRoute = '/';
  private myUsername = '';
  private myConnectionId = '';
  private started = false;

  /** Map of connectionId → PresencePeer. */
  private readonly _peers = signal<ReadonlyMap<string, PresencePeer>>(new Map());

  /** All non-self peers heard from recently. */
  readonly peers = computed(() => {
    const cutoff = Date.now() - STALE_AFTER_MS;
    return [...this._peers().values()]
      .filter((p) => p.lastSeen >= cutoff && p.connectionId !== this.myConnectionId)
      .sort((a, b) => a.username.localeCompare(b.username));
  });

  /** Peers on the same route as the current user. */
  readonly peersOnSameRoute = computed(() =>
    this.peers().filter((p) => p.route === this.currentRoute),
  );

  start(): void {
    if (this.started) return;
    this.started = true;

    this.auth.currentUser$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((user) => {
        this.myUsername = user?.username ?? '';
      });

    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => {
        this.currentRoute = this.normaliseRoute(
          (e as NavigationEnd).urlAfterRedirects,
        );
        // Heartbeat immediately on route change so other tabs don't
        // wait the full HEARTBEAT_MS to see us move.
        this.heartbeat();
      });

    this.realtime
      .subscribeTopic<{
        route?: string;
        _publisher?: { username?: string; connection_id?: string };
      }>(TOPIC)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((update) => {
        const pub = update.payload?._publisher;
        if (!pub?.connection_id) return;
        // Remember our own connection id so we can filter self.
        if (pub.username === this.myUsername && !this.myConnectionId) {
          this.myConnectionId = pub.connection_id;
        }
        const next = new Map(this._peers());
        next.set(pub.connection_id, {
          username: pub.username || 'unknown',
          route: update.payload?.route ?? '/',
          lastSeen: Date.now(),
          connectionId: pub.connection_id,
        });
        this._peers.set(next);
      });

    interval(HEARTBEAT_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.heartbeat());

    // Fire one immediately so the first render isn't blank.
    this.heartbeat();

    // Periodically sweep stale rows out so the signal computation
    // stays cheap even after long sessions.
    interval(STALE_AFTER_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        const cutoff = Date.now() - STALE_AFTER_MS;
        const next = new Map(this._peers());
        let changed = false;
        for (const [id, p] of next) {
          if (p.lastSeen < cutoff) {
            next.delete(id);
            changed = true;
          }
        }
        if (changed) this._peers.set(next);
      });
  }

  // ── helpers ────────────────────────────────────────────────────────

  private heartbeat(): void {
    if (!this.myUsername) return;
    if (typeof navigator !== 'undefined' && !navigator.onLine) return;
    this.realtime.publish(TOPIC, 'heartbeat', {
      route: this.currentRoute,
      username: this.myUsername,
    });
  }

  private normaliseRoute(url: string): string {
    return (url ?? '/').split('?')[0].split('#')[0];
  }
}
