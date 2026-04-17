import { Injectable, NgZone, inject } from '@angular/core';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { filter, fromEvent, merge, throttleTime } from 'rxjs';

import { AuthService } from './auth.service';
import {
  SessionTimeoutWarningDialogComponent,
  SessionTimeoutWarningData,
  SessionTimeoutWarningResult,
} from './session-timeout-warning-dialog.component';

/**
 * Phase E2 / Gap 42 — proactive session-timeout warning.
 *
 * Complements Phase U1 / Gap 14's reauth dialog. The reauth dialog is
 * REACTIVE — fired on 401 after the token has already expired. This
 * service is PROACTIVE — it fires two minutes before expiry so the user
 * can keep working without losing form state.
 *
 * Assumptions (documented, easy to change):
 *   - Tokens are long-lived (Gap 14 decision — 12h server-side lifetime).
 *   - The server-side TTL is not exposed to the client, so we track
 *     issuance client-side via `AuthService.markTokenRefreshed()` +
 *     `getTokenIssuedAt()`.
 *   - Client-side activity (keystroke, click) silently extends the
 *     window — identical behaviour to most SaaS products.
 *
 * Lifecycle:
 *   - `start()` — called once from `app.component.ts` ngOnInit. Wires
 *     the activity listener and arms the warning timer.
 *   - When `issued_at + TOKEN_LIFETIME_MS - WARNING_WINDOW_MS` is
 *     reached, opens the warning dialog.
 *   - The dialog resolves with one of three outcomes:
 *       `stay`    — call `auth.markTokenRefreshed()`, rearm.
 *       `signout` — call `auth.logout()`, stop.
 *       `expired` — user ignored the countdown. Stop; the next HTTP
 *                   call will 401 and Gap 14 reauth takes over.
 *   - Activity during the warning window silently extends the session
 *     (dismisses the dialog and rearms).
 *
 * Runs outside the Angular zone for the ambient activity listener so
 * we don't trigger change detection on every mouse move / keypress.
 */

/** Long-lived token lifetime. Mirrors Gap 14's "long-lived" decision —
 *  kept in sync with Django REST Framework's default token + whatever
 *  session-lifetime the backend enforces. If the backend grows a proper
 *  `/api/auth/token-info/` endpoint, read the TTL from there instead. */
const TOKEN_LIFETIME_MS = 12 * 60 * 60 * 1000; // 12 hours

/** How early we raise the warning. */
const WARNING_WINDOW_MS = 2 * 60 * 1000; // 2 minutes

/** Throttle ambient activity-based extensions so we don't thrash the
 *  timer on every keystroke. Any one event extends the session; further
 *  events in the same 30s window are ignored. */
const ACTIVITY_THROTTLE_MS = 30_000;

@Injectable({ providedIn: 'root' })
export class SessionTimeoutService {
  private readonly auth = inject(AuthService);
  private readonly dialog = inject(MatDialog);
  private readonly zone = inject(NgZone);

  private armed = false;
  private warningTimer: ReturnType<typeof setTimeout> | null = null;
  /** Typed with the dialog's result shape so `afterClosed()` resolves
   *  to a `SessionTimeoutWarningResult`, not `unknown`. */
  private warningDialogRef: MatDialogRef<
    SessionTimeoutWarningDialogComponent,
    SessionTimeoutWarningResult
  > | null = null;

  /** Call once from app bootstrap. Safe to call repeatedly — subsequent
   *  calls are no-ops. */
  start(): void {
    if (this.armed) return;
    this.armed = true;

    // Rearm whenever the user is actually doing something — keystroke,
    // click, mousemove. This is the "silent extension" path.
    this.zone.runOutsideAngular(() => {
      merge(
        fromEvent(document, 'keydown', { passive: true }),
        fromEvent(document, 'click', { passive: true }),
        fromEvent(document, 'mousemove', { passive: true }),
      )
        .pipe(
          // Only count activity while the user is actually authenticated.
          filter(() => this.auth.getToken() !== null),
          throttleTime(ACTIVITY_THROTTLE_MS, undefined, { leading: true, trailing: false }),
        )
        .subscribe(() => this.onActivity());
    });

    this.arm();
  }

  /** (Re)schedule the warning dialog based on the current token issuance
   *  timestamp. Clears any previous pending timer. */
  private arm(): void {
    if (this.warningTimer) {
      clearTimeout(this.warningTimer);
      this.warningTimer = null;
    }
    if (this.auth.getToken() === null) {
      return; // Not signed in — nothing to warn about.
    }

    const issuedAt = this.auth.getTokenIssuedAt() ?? Date.now();
    const expiresAt = issuedAt + TOKEN_LIFETIME_MS;
    const warnAt = expiresAt - WARNING_WINDOW_MS;
    const delay = Math.max(0, warnAt - Date.now());

    // setTimeout inside the zone is fine here — one scheduled call, no
    // high-frequency work.
    this.warningTimer = setTimeout(() => this.openWarning(expiresAt), delay);
  }

  /** Activity extends the session. If the warning dialog is open, close
   *  it with `stay` and rearm; otherwise just rearm. */
  private onActivity(): void {
    if (this.warningDialogRef) {
      // Activity during the 2-minute window is implicit consent to stay.
      this.warningDialogRef.close({ choice: 'stay' });
      // The dialog's afterClosed handler will call extend() + rearm().
      return;
    }
    // Normal path: user is typing/clicking well before the warning fires.
    // Reset the anchor so the warning time slides forward.
    this.auth.markTokenRefreshed();
    this.arm();
  }

  /** Open the warning dialog and handle the user's choice. */
  private openWarning(expiresAt: number): void {
    if (this.warningDialogRef) return;

    // Guard — if the token has already expired between scheduling and
    // firing (laptop sleeping, clock drift), skip the warning and let
    // the next 401 drive the reauth dialog.
    if (Date.now() >= expiresAt) {
      return;
    }

    // Re-enter the zone so Material dialog change detection behaves.
    this.zone.run(() => {
      const ref = this.dialog.open<
        SessionTimeoutWarningDialogComponent,
        SessionTimeoutWarningData,
        SessionTimeoutWarningResult
      >(SessionTimeoutWarningDialogComponent, {
        width: '420px',
        disableClose: true,
        autoFocus: 'first-heading',
        closeOnNavigation: false,
        data: {
          expiresAt,
          windowMs: WARNING_WINDOW_MS,
        },
      });
      this.warningDialogRef = ref;

      ref.afterClosed().subscribe((result) => {
        this.warningDialogRef = null;
        switch (result?.choice) {
          case 'stay':
            this.extend();
            break;
          case 'signout':
            this.auth.logout();
            break;
          case 'expired':
          default:
            // User let the countdown hit zero. Do nothing — the next HTTP
            // call will 401 and Gap 14 reauth dialog takes over.
            break;
        }
      });
    });
  }

  /** Public hand-off used by the "Stay signed in" button (via onActivity
   *  internally). Exposed so other code paths — e.g. a global "extend my
   *  session" button — can reuse the same logic. */
  extend(): void {
    this.auth.markTokenRefreshed();
    this.arm();
  }
}
