import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable, catchError, of } from 'rxjs';
import { RealtimeService } from './realtime.service';

/**
 * Phase SR — Suggestion Readiness Gate client.
 *
 * Holds the current readiness verdict returned by
 * `GET /api/suggestions/readiness/` plus a live subscription to the
 * `suggestions.readiness` real-time topic (Phase R0). Any page that
 * wants to block or warn based on readiness reads `ready()` /
 * `blocking()` / `prerequisites()` as signals.
 *
 * No new Angular state — every source of truth lives on the backend.
 * This service is just the cache + realtime glue.
 */

export type PrerequisiteStatus =
  | 'ready'
  | 'running'
  | 'stale'
  | 'blocked'
  | 'not_configured';

export interface Prerequisite {
  id: string;
  category: string;
  name: string;
  status: PrerequisiteStatus;
  plain_english: string;
  next_step: string;
  progress: number;
  affects: string[];
}

export interface ReadinessPayload {
  ready: boolean;
  prerequisites: Prerequisite[];
  blocking: Prerequisite[];
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class SuggestionReadinessService {
  private http = inject(HttpClient);
  private realtime = inject(RealtimeService);
  private destroyRef = inject(DestroyRef);

  private readonly _payload = signal<ReadinessPayload | null>(null);
  private readonly _loading = signal<boolean>(false);
  private readonly _error = signal<string | null>(null);

  readonly payload = this._payload.asReadonly();
  readonly loading = this._loading.asReadonly();
  readonly error = this._error.asReadonly();

  /** Defaults to `false` while the first request is in flight so the
   *  Review page blocks by default — safer than flashing stale rows. */
  readonly ready = computed(() => this._payload()?.ready ?? false);
  readonly prerequisites = computed(
    () => this._payload()?.prerequisites ?? [],
  );
  readonly blocking = computed(() => this._payload()?.blocking ?? []);
  readonly updatedAt = computed(() => this._payload()?.updated_at ?? '');

  /** Fetch once + subscribe to realtime prereq changes. Idempotent. */
  start(): void {
    this.refresh().subscribe();
    this.realtime
      .subscribeTopic('suggestions.readiness')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        // Any prereq change broadcast → re-fetch the canonical payload.
        // Keeps the dedup logic server-side and the client tiny.
        this.refresh().subscribe();
      });
  }

  refresh(): Observable<ReadinessPayload | null> {
    this._loading.set(true);
    return this.http
      .get<ReadinessPayload>('/api/suggestions/readiness/')
      .pipe(
        catchError((err) => {
          this._error.set(this.explain(err));
          return of(null);
        }),
      )
      .pipe(
        // `tap` inlined so we avoid the extra import — side effects on
        // both success and the caught error path.
        (source) =>
          new Observable<ReadinessPayload | null>((subscriber) => {
            const sub = source.subscribe({
              next: (value) => {
                this._loading.set(false);
                if (value) {
                  this._payload.set(value);
                  this._error.set(null);
                }
                subscriber.next(value);
              },
              error: (err) => {
                this._loading.set(false);
                subscriber.error(err);
              },
              complete: () => subscriber.complete(),
            });
            return () => sub.unsubscribe();
          }),
      );
  }

  private explain(err: unknown): string {
    if (!err || typeof err !== 'object') return 'Could not reach readiness endpoint.';
    const e = err as { status?: number };
    if (e.status === 401) return 'Session expired — please sign in.';
    if (e.status && e.status >= 500) return 'Readiness service is down.';
    return 'Could not reach readiness endpoint.';
  }
}
