/**
 * Optimistic UI helper — Phase U1 / Gap 7.
 *
 * Runs a local state mutation immediately, awaits a server call, and
 * rolls back the mutation if the server errors. Centralises the three
 * places in the app that currently do this inline (with subtle bugs
 * when `next()` and `error()` both edit the same array).
 *
 * Usage (component method):
 *
 *   toggle(item: Thing): void {
 *     optimistic(
 *       () => { item.enabled = !item.enabled; },       // apply
 *       () => { item.enabled = !item.enabled; },       // rollback
 *       () => this.api.patch(item.id, { enabled: item.enabled }),
 *       {
 *         onError: () => this.snack.open('Could not save.', 'Dismiss', { duration: 4000 }),
 *       },
 *     );
 *   }
 *
 * Design choices:
 *   - Returns a `Promise<void>` so callers can `await` if they want, but
 *     there's no contract to do so (fire-and-forget is valid).
 *   - `apply` and `rollback` are supplied as pairs rather than a single
 *     "state diff" because the calling component already has the read +
 *     write logic and understands immutability patterns best.
 *   - Rollback runs before `onError` so the UI is consistent before the
 *     snackbar appears.
 *   - Never rethrows — the HTTP error is handled here. Callers that
 *     need the original error can use `onError`.
 */

import { firstValueFrom, Observable } from 'rxjs';

export interface OptimisticOptions {
  /** Called on server success. Receives the server response. */
  onSuccess?: (result: unknown) => void;
  /** Called on server failure, AFTER the rollback has run. */
  onError?: (err: unknown) => void;
  /** Called in both success and failure paths, regardless of outcome. */
  onSettled?: () => void;
}

export async function optimistic<TResult>(
  apply: () => void,
  rollback: () => void,
  serverCall: () => Observable<TResult> | Promise<TResult>,
  options: OptimisticOptions = {},
): Promise<void> {
  // 1. Apply immediately.
  try {
    apply();
  } catch (err) {
    // Apply itself failed — nothing to roll back, just report.
    options.onError?.(err);
    options.onSettled?.();
    return;
  }

  // 2. Fire the server call.
  try {
    const outcome = serverCall();
    const result: TResult =
      outcome instanceof Promise
        ? await outcome
        : await firstValueFrom(outcome);
    options.onSuccess?.(result);
  } catch (err) {
    // 3. Rollback on error.
    try {
      rollback();
    } catch {
      // A broken rollback is a real bug; surface it on the console.
      // We still call `onError` below so the user sees the original error.
       
      console.error('[optimistic] rollback threw while handling server error:', err);
    }
    options.onError?.(err);
  } finally {
    options.onSettled?.();
  }
}
