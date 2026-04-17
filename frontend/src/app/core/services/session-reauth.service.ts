import { Injectable, inject } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { Observable, firstValueFrom } from 'rxjs';

import { SessionReauthDialogComponent, SessionReauthResult } from './session-reauth-dialog.component';

/**
 * Phase U1 / Gap 14 — Silent re-auth prompt for expired tokens.
 *
 * When the auth interceptor sees a 401, it calls `prompt()` instead of
 * hard-redirecting to `/login`. The user gets a small dialog asking them
 * to re-enter their password (username stays pre-filled from the last
 * session in localStorage). On success the new token is stashed and the
 * request that triggered the 401 can be retried; on cancel, the
 * interceptor falls through to the legacy login redirect.
 *
 * Why dialog vs full page redirect:
 *   - Current Angular state (forms, scroll position, open panels) survives
 *     a re-auth — the user is not yanked to a different route mid-edit.
 *   - Feels like re-entering a password, not losing your place.
 *
 * Why deduplicate:
 *   - A page that fires N parallel HTTP calls can see N 401 responses.
 *     The service guarantees ONE dialog — every concurrent caller gets
 *     back the same in-flight promise.
 */
@Injectable({ providedIn: 'root' })
export class SessionReauthService {
  private readonly dialog = inject(MatDialog);

  /** Currently-active prompt, if any. Resolves `true` on success,
   *  `false` on cancel. Cleared once the dialog closes. */
  private inflight: Promise<boolean> | null = null;

  /**
   * Open the re-auth dialog (or return the in-flight promise if one is
   * already open). Resolves with `true` when the user successfully
   * re-authenticated, `false` when they cancelled.
   */
  prompt(): Promise<boolean> {
    if (this.inflight) return this.inflight;

    const ref = this.dialog.open<SessionReauthDialogComponent, void, SessionReauthResult>(
      SessionReauthDialogComponent,
      {
        width: '400px',
        disableClose: true,      // force an explicit choice
        autoFocus: 'first-heading',
        closeOnNavigation: false,
      },
    );

    this.inflight = firstValueFrom(ref.afterClosed() as Observable<SessionReauthResult | undefined>)
      .then((result) => {
        this.inflight = null;
        return result?.success === true;
      })
      .catch(() => {
        this.inflight = null;
        return false;
      });

    return this.inflight;
  }
}
