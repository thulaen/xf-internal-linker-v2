/**
 * rx-cache — RxJS caching primitives for services.
 *
 * Phase U2 / Gaps 13 + 20.
 *
 * - `cached(source)` — request deduplication. Two subscribers within
 *   the same emission window share ONE HTTP call. Implemented via
 *   `shareReplay(1)` with `resetOnRefCountZero: true` so a completed
 *   observable with zero subscribers is GC'd. Use for inexpensive
 *   GETs that don't change for the life of a subscription.
 *
 * - `swr<T>({ fetcher, ttlMs })` — stale-while-revalidate cache:
 *   returns the cached value immediately if we have one AND it's
 *   younger than `ttlMs`; otherwise kicks off a fresh fetch. Callers
 *   subscribe to `cache$` to see both the cached hit and the later
 *   revalidated value. Use for data that rarely changes but must
 *   still eventually refresh (settings, user profile, weight lists).
 *
 * Why not use @ngrx/data / tanstack-query: the project already has a
 * pile of hand-rolled service methods. These tiny primitives slot
 * into existing services with a one-line wrap, no framework bet.
 */

import {
  BehaviorSubject,
  Observable,
  Subject,
  defer,
  filter,
  merge,
  shareReplay,
  take,
  tap,
} from 'rxjs';

/**
 * Request deduplication for an Observable-returning producer.
 *
 * Wraps the source in `shareReplay({ bufferSize: 1, refCount: true })`.
 * N components subscribing to the returned Observable share ONE
 * upstream execution; once they all unsubscribe, the next subscriber
 * re-executes the source.
 *
 * Example (in a service):
 *   getSettings(): Observable<Settings> {
 *     return cached(this.http.get<Settings>('/api/settings'));
 *   }
 *
 * Gap 13 reference implementation.
 */
export function cached<T>(source: Observable<T>): Observable<T> {
  return source.pipe(
    shareReplay({ bufferSize: 1, refCount: true }),
  );
}

// ─────────────────────────────────────────────────────────────────────
// Stale-while-revalidate cache (Gap 20)
// ─────────────────────────────────────────────────────────────────────

export interface SwrCache<T> {
  /** Observable of current cached value. Emits on cache fill + refresh. */
  readonly value$: Observable<T | null>;
  /** Snapshot of the last-known value. `null` if never fetched. */
  get(): T | null;
  /** Fire the fetcher and update the cache. Returns the fresh value. */
  refresh(): Observable<T>;
  /** Ensure a value exists. If stale or missing, fetch; otherwise return
   *  the cached value immediately. Use this as the primary read path. */
  get$(): Observable<T>;
  /** Wipe the cache. Next `get$()` will fetch. */
  invalidate(): void;
}

export interface SwrOptions<T> {
  /** Producer for a fresh value. Called on first read and after TTL. */
  fetcher: () => Observable<T>;
  /** How long a cached value stays fresh (ms). Default 30 seconds. */
  ttlMs?: number;
}

/**
 * Build a stale-while-revalidate cache around a fetcher.
 *
 * Behaviour:
 *   - `get$()` returns the cached value IMMEDIATELY if fresh.
 *     If stale or missing, it emits the cached value first (if any),
 *     then the fresh value once the fetch resolves.
 *   - `refresh()` forces a new fetch, regardless of freshness.
 *   - `invalidate()` clears the cache.
 *   - Concurrent reads share one in-flight fetch — multiple callers
 *     during a refresh don't hit the backend N times.
 *
 * Example:
 *   private readonly settingsCache = swr<Settings>({
 *     fetcher: () => this.http.get<Settings>('/api/settings'),
 *     ttlMs: 60_000,
 *   });
 *
 *   getSettings(): Observable<Settings> {
 *     return this.settingsCache.get$();
 *   }
 *
 *   onSettingsSaved(): void {
 *     this.settingsCache.invalidate();
 *   }
 */
export function swr<T>(options: SwrOptions<T>): SwrCache<T> {
  const ttlMs = options.ttlMs ?? 30_000;
  const state = new BehaviorSubject<T | null>(null);
  let lastFetchedAt = 0;
  let inflight: Observable<T> | null = null;

  const runFetch = (): Observable<T> => {
    if (inflight) return inflight;
    inflight = defer(() => options.fetcher()).pipe(
      tap({
        next: (value) => {
          state.next(value);
          lastFetchedAt = Date.now();
        },
        finalize: () => {
          inflight = null;
        },
      }),
      shareReplay({ bufferSize: 1, refCount: true }),
    );
    return inflight;
  };

  const isFresh = (): boolean => {
    if (state.value === null) return false;
    return Date.now() - lastFetchedAt < ttlMs;
  };

  return {
    value$: state.asObservable(),

    get(): T | null {
      return state.value;
    },

    refresh(): Observable<T> {
      return runFetch();
    },

    get$(): Observable<T> {
      // Three paths:
      //   1. Fresh cache → emit current value (one emission, complete).
      //   2. Stale cache + value present → emit cached value first, then
      //      the revalidated value once the fetch resolves.
      //   3. No cache → just the fetch result.
      if (isFresh()) {
        // `value$` is non-null here because isFresh() guaranteed it.
        // Narrow the type and take one so the caller's subscribe
        // completes after the single synchronous emission.
        return state.asObservable().pipe(
          filter((v): v is T => v !== null),
          take(1),
        );
      }

      const hadValue = state.value !== null;
      const staleEmission: Observable<T> = hadValue
        ? state.asObservable().pipe(filter((v): v is T => v !== null), take(1))
        : (new Subject<T>().asObservable());
      const freshEmission = runFetch();

      return hadValue ? merge(staleEmission, freshEmission) : freshEmission;
    },

    invalidate(): void {
      state.next(null);
      lastFetchedAt = 0;
    },
  };
}
