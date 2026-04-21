import {
  DestroyRef,
  Injectable,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval } from 'rxjs';
import { VisibilityGateService } from '../util/visibility-gate.service';

import { AuthService } from './auth.service';
import { RealtimeService } from './realtime.service';

/**
 * Phase RC / Gap 141 — Soft-lock service.
 *
 * Two operators editing the same suggestion / settings card / weight
 * is fine in principle (last-write-wins), but they should KNOW about
 * each other before they both Save and clobber one another's change.
 *
 * This service lets a component "claim" a soft lock on an entity:
 *
 *   onEdit() {
 *     this.lockSvc.claim('suggestion', this.id);
 *   }
 *
 * Soft = not enforced server-side. Other tabs/users see the claim
 * via the `lock.<type>.<id>` topic and render a banner. The
 * SoftLockBannerComponent surfaces the warning where the user can
 * see it.
 *
 * Heartbeats every 10s while a lock is held. Lock auto-releases
 * after 30s of silence (a tab closed mid-edit doesn't strand the
 * banner forever).
 */

const HEARTBEAT_MS = 10_000;
const STALE_MS = 30_000;

interface LockHolder {
  username: string;
  lastSeen: number;
  connectionId: string;
}

@Injectable({ providedIn: 'root' })
export class SoftLockService {
  private readonly auth = inject(AuthService);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly visibilityGate = inject(VisibilityGateService);

  private myUsername = '';
  private myConnectionId = '';

  /** Map of `<type>:<id>` → list of holders. */
  private readonly _locks = signal<ReadonlyMap<string, LockHolder[]>>(new Map());

  /** Active claims by THIS tab (so we can release on destroy). */
  private readonly mine = new Map<string, ReturnType<typeof setInterval>>();

  constructor() {
    this.auth.currentUser$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => (this.myUsername = u?.username ?? ''));

    // Sweep stale entries periodically. Gated by
    // `VisibilityGateService` — if the tab is hidden there's no UI to
    // update. See docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() => interval(HEARTBEAT_MS))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.sweep());
  }

  /** Returns the list of OTHER holders of a given lock (excluding
   *  this tab + this user). The component renders a banner when the
   *  signal is non-empty. */
  othersHolding(targetType: string, targetId: string | number): { username: string }[] {
    const key = this.keyOf(targetType, targetId);
    const all = this._locks().get(key) ?? [];
    const cutoff = Date.now() - STALE_MS;
    return all
      .filter((h) => h.lastSeen >= cutoff)
      .filter((h) => h.connectionId !== this.myConnectionId)
      .map((h) => ({ username: h.username }));
  }

  /** Claim a soft lock. Idempotent — calling twice keeps the
   *  existing claim alive instead of double-broadcasting. */
  claim(targetType: string, targetId: string | number): void {
    const key = this.keyOf(targetType, targetId);
    if (this.mine.has(key)) return;
    const topic = this.topicOf(targetType, targetId);
    // Ensure we're subscribed so we hear other holders' heartbeats too.
    this.realtime
      .subscribeTopic<{
        action?: 'claim' | 'release';
        _publisher?: { username?: string; connection_id?: string };
      }>(topic)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => this.absorb(key, u.payload));

    const send = () => {
      if (!this.myUsername) return;
      // Skip when the tab is hidden — the soft-lock naturally expires
      // after STALE_MS on other tabs, which is the intended UX (lock
      // follows attention). See docs/PERFORMANCE.md §13.
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      this.realtime.publish(topic, 'claim', {
        username: this.myUsername,
        target_type: targetType,
        target_id: String(targetId),
      });
    };
    send();
    this.mine.set(key, setInterval(send, HEARTBEAT_MS));
  }

  /** Release a soft lock. */
  release(targetType: string, targetId: string | number): void {
    const key = this.keyOf(targetType, targetId);
    const handle = this.mine.get(key);
    if (!handle) return;
    clearInterval(handle);
    this.mine.delete(key);
    this.realtime.publish(this.topicOf(targetType, targetId), 'release', {
      username: this.myUsername,
      target_type: targetType,
      target_id: String(targetId),
    });
  }

  // ── internals ──────────────────────────────────────────────────────

  private absorb(
    key: string,
    payload: { action?: 'claim' | 'release'; _publisher?: { username?: string; connection_id?: string } },
  ): void {
    const pub = payload?._publisher;
    if (!pub?.connection_id) return;
    if (pub.username === this.myUsername && !this.myConnectionId) {
      this.myConnectionId = pub.connection_id;
    }
    const next = new Map(this._locks());
    const existing = [...(next.get(key) ?? [])];
    const idx = existing.findIndex((h) => h.connectionId === pub.connection_id);
    if (payload?.action === 'release') {
      if (idx >= 0) existing.splice(idx, 1);
    } else {
      const entry: LockHolder = {
        username: pub.username || 'unknown',
        lastSeen: Date.now(),
        connectionId: pub.connection_id,
      };
      if (idx >= 0) existing[idx] = entry;
      else existing.push(entry);
    }
    if (existing.length === 0) next.delete(key);
    else next.set(key, existing);
    this._locks.set(next);
  }

  private sweep(): void {
    const cutoff = Date.now() - STALE_MS;
    let changed = false;
    const next = new Map(this._locks());
    for (const [key, holders] of next) {
      const fresh = holders.filter((h) => h.lastSeen >= cutoff);
      if (fresh.length !== holders.length) {
        changed = true;
        if (fresh.length === 0) next.delete(key);
        else next.set(key, fresh);
      }
    }
    if (changed) this._locks.set(next);
  }

  private keyOf(t: string, id: string | number): string {
    return `${t}:${id}`;
  }

  private topicOf(t: string, id: string | number): string {
    // Sanitise — backend topic permission only allows `lock.*`.
    return `lock.${t.replace(/[^a-z0-9_-]/gi, '_')}.${String(id).replace(/[^a-z0-9_-]/gi, '_')}`;
  }
}
