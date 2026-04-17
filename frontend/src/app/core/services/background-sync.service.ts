import { DestroyRef, Injectable, inject } from '@angular/core';

import { OfflineStoreService } from './offline-store.service';

/**
 * Phase F1 / Gap 88 — Background Sync queue for outbound writes.
 *
 * When the browser is offline (or the user's POST fails with a
 * network error), instead of throwing the data away, we enqueue it
 * in IndexedDB and replay it on the next `online` event.
 *
 * Design notes:
 *   - Uses the same OfflineStoreService for persistence (one DB,
 *     two stores would have been cleaner but the queue is small
 *     enough — single-key serialised array — to share a key).
 *   - Doesn't use the platform's SyncManager / Background Sync API
 *     directly because that's only available inside service workers
 *     and the queue belongs to the app code that knows what to retry.
 *     We fire on the `online` window event which works in every
 *     browser and doesn't require service worker plumbing.
 *   - Replay strategy is naive: drain the queue in FIFO order until
 *     a request fails, at which point we re-queue the failed one and
 *     stop until the next `online` event. Avoids hammering a flaky
 *     network with a stampede of retries.
 *
 * Idempotency is the caller's responsibility — only enqueue requests
 * that are safe to replay. Don't queue payment captures.
 *
 * Public API:
 *   await sync.enqueue({ method: 'POST', url: '/x', body: {...} });
 *   sync.start();   // wires the 'online' listener — call once at boot
 */

const QUEUE_KEY = 'background-sync-queue';

export interface QueuedRequest {
  /** Stable id used for dedup + cancellation. */
  id: string;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  url: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** When the request was first enqueued. */
  queuedAt: number;
  /** How many replay attempts have already failed. */
  attempts: number;
}

@Injectable({ providedIn: 'root' })
export class BackgroundSyncService {
  private readonly store = inject(OfflineStoreService);
  private readonly destroyRef = inject(DestroyRef);
  private started = false;
  private draining = false;

  /** Wire once from app bootstrap. Subsequent calls are no-ops. */
  start(): void {
    if (this.started) return;
    this.started = true;
    if (typeof window === 'undefined') return;
    const onOnline = () => {
      void this.drain();
    };
    window.addEventListener('online', onOnline);
    this.destroyRef.onDestroy(() => {
      window.removeEventListener('online', onOnline);
    });
    // Drain on boot too — the user may have queued requests in a
    // previous session.
    if (navigator.onLine) {
      void this.drain();
    }
  }

  /** Enqueue a write. Returns when it's been persisted to IndexedDB
   *  (or the in-memory fallback when IDB isn't available). */
  async enqueue(req: Omit<QueuedRequest, 'id' | 'queuedAt' | 'attempts'>): Promise<void> {
    const item: QueuedRequest = {
      id: this.makeId(),
      method: req.method,
      url: req.url,
      body: req.body,
      headers: req.headers,
      queuedAt: Date.now(),
      attempts: 0,
    };
    const queue = await this.readQueue();
    queue.push(item);
    await this.writeQueue(queue);
    // If we're online right now, try draining immediately so the
    // queued item doesn't sit in storage longer than necessary.
    if (typeof navigator !== 'undefined' && navigator.onLine) {
      void this.drain();
    }
  }

  /** Snapshot of current queued items — useful for diagnostics UI. */
  async list(): Promise<readonly QueuedRequest[]> {
    return this.readQueue();
  }

  /** Wipe the queue. Wired to logout + Emergency Stop. */
  async clear(): Promise<void> {
    await this.writeQueue([]);
  }

  // ── internals ──────────────────────────────────────────────────────

  private async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    try {
      const queue = await this.readQueue();
      while (queue.length > 0) {
        const next = queue[0];
        const ok = await this.send(next);
        if (!ok) {
          // Bump attempts and re-queue at the head; stop until next
          // online event. (Drop items that have failed >= 5 times to
          // avoid an unbounded queue.)
          next.attempts += 1;
          if (next.attempts >= 5) {
            queue.shift();
          } else {
            queue[0] = next;
          }
          await this.writeQueue(queue);
          return;
        }
        queue.shift();
        await this.writeQueue(queue);
      }
    } finally {
      this.draining = false;
    }
  }

  private async send(item: QueuedRequest): Promise<boolean> {
    try {
      const init: RequestInit = {
        method: item.method,
        headers: { 'Content-Type': 'application/json', ...(item.headers ?? {}) },
        credentials: 'same-origin',
      };
      if (item.body !== undefined) {
        init.body = typeof item.body === 'string' ? item.body : JSON.stringify(item.body);
      }
      const res = await fetch(item.url, init);
      // Anything in the 2xx/3xx range is "delivered enough" — even a
      // 304 means the server got our payload.
      return res.status < 400;
    } catch {
      return false;
    }
  }

  private async readQueue(): Promise<QueuedRequest[]> {
    const cached = await this.store.get<QueuedRequest[]>(QUEUE_KEY);
    return cached?.value ?? [];
  }

  private async writeQueue(queue: QueuedRequest[]): Promise<void> {
    await this.store.put(QUEUE_KEY, queue);
  }

  private makeId(): string {
    return (
      Date.now().toString(36) +
      '-' +
      Math.random().toString(36).slice(2, 10)
    );
  }
}
