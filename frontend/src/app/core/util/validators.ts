/**
 * Phase E2 / Gap 48 — debounced async validators.
 *
 * Async validators in Angular fire on every value change unless you debounce
 * them yourself. A "username availability" check typed at 40 WPM can easily
 * fire 10 HTTP requests in two seconds — the server answers only the last
 * one matters.
 *
 * This utility wraps an AbstractControl-aware async fn in a Subject-based
 * debounce so Angular's validator lifecycle waits for quiet keystrokes.
 *
 * Usage:
 *
 *   import { debouncedAsyncValidator } from '../core/util/validators';
 *
 *   usernameAvailable = debouncedAsyncValidator<string>(
 *     (value) => this.userSvc.checkUsername(value),
 *     400,
 *   );
 *
 *   // In a form:
 *   username = new FormControl(
 *     '',
 *     { asyncValidators: [this.usernameAvailable], updateOn: 'change' },
 *   );
 *
 *   // Service contract — return one of:
 *   //   null                  = valid
 *   //   ValidationErrors obj  = invalid (e.g. { taken: true })
 *   //   rejection / error     = treated as "valid" (don't penalise the
 *   //                           user for a flaky network)
 */

import { AbstractControl, AsyncValidatorFn, ValidationErrors } from '@angular/forms';
import { Observable, Subject, of, timer } from 'rxjs';
import { catchError, debounce, map, switchMap, take } from 'rxjs';

/**
 * Wrap an async check in a debounced AsyncValidatorFn.
 *
 * @param fetcher - Given the current control value, return an Observable
 *                  that emits `ValidationErrors` for invalid or `null` for
 *                  valid. Errors on the observable are swallowed (returns
 *                  valid) so a server outage doesn't block form submit.
 * @param debounceMs - Milliseconds of quiet keystrokes before hitting the
 *                     server. Default 400ms — a typical sweet spot. Tune
 *                     up for expensive checks, down for local fetches.
 */
export function debouncedAsyncValidator<T = unknown>(
  fetcher: (value: T) => Observable<ValidationErrors | null>,
  debounceMs = 400,
): AsyncValidatorFn {
  const input$ = new Subject<T>();

  // A long-lived pipeline that resolves per-value. Angular subscribes to
  // the returned Observable once per validation attempt; we feed the
  // latest value through the subject and wait for the debounce window
  // to settle before calling `fetcher`.
  const output$ = input$.pipe(
    debounce(() => timer(debounceMs)),
    switchMap((value) =>
      fetcher(value).pipe(
        // Network hiccups => treat as valid so the user isn't stuck.
        catchError(() => of(null)),
      ),
    ),
  );

  return (control: AbstractControl): Observable<ValidationErrors | null> => {
    // Fresh subject per call? No — we reuse the shared input$/output$ so
    // rapid typing is debounced across attempts. We take(1) so each
    // AsyncValidator invocation completes once a result lands.
    const result$ = output$.pipe(take(1), map((v) => v));
    // Enqueue the current control value AFTER subscribing to output$ so
    // we don't lose the emission. Microtask-delayed via setTimeout(0).
    setTimeout(() => input$.next(control.value as T), 0);
    return result$;
  };
}

/**
 * Composes a sync predicate into an async validator, useful when you have
 * a fast local check (e.g. regex, length) that you still want debounced
 * behavior for (to delay error display until the user stops typing).
 *
 * Example:
 *   slugFormat = debouncedSyncValidator<string>(
 *     (value) => /^[a-z0-9-]+$/.test(value) ? null : { invalidSlug: true },
 *     250,
 *   );
 */
export function debouncedSyncValidator<T = unknown>(
  predicate: (value: T) => ValidationErrors | null,
  debounceMs = 250,
): AsyncValidatorFn {
  return debouncedAsyncValidator<T>(
    (value) => of(predicate(value)),
    debounceMs,
  );
}
