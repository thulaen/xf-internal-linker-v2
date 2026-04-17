import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, switchMap, tap, catchError, of, map } from 'rxjs';

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  date_joined: string;
}

/** Shared constant — also used by auth.interceptor.ts */
export const TOKEN_KEY = 'xfil_auth_token';

/**
 * Phase E2 / Gap 42 — timestamp (ms) the current token was issued/refreshed.
 * SessionTimeoutService reads this to compute when to open the warning.
 * Written on successful login and by `markTokenRefreshed()`.
 */
export const TOKEN_ISSUED_AT_KEY = 'xfil_auth_token_issued_at';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private currentUserSub = new BehaviorSubject<AuthUser | null>(null);
  private checkingSub = new BehaviorSubject<boolean>(true);

  currentUser$ = this.currentUserSub.asObservable();
  isLoggedIn$ = this.currentUser$.pipe(map(u => u !== null));
  isChecking$ = this.checkingSub.asObservable();

  constructor() {
    this.initAuth();
  }

  private initAuth(): void {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      this.checkingSub.next(false);
      return;
    }
    this.http.get<AuthUser>('/api/auth/me/')
      .pipe(
        tap(user => {
          this.currentUserSub.next(user);
          this.checkingSub.next(false);
          // Gap 42 — if we have a valid token but no issued-at stamp
          // (legacy session from before Gap 42 shipped), anchor it now
          // so SessionTimeoutService can schedule the warning. Worst
          // case: the user sees a 12h countdown instead of whatever was
          // remaining on the real token; they can still extend freely.
          if (this.getTokenIssuedAt() === null) {
            this.markTokenRefreshed();
          }
        }),
        catchError(() => {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(TOKEN_ISSUED_AT_KEY);
          this.currentUserSub.next(null);
          this.checkingSub.next(false);
          return of(null);
        })
      )
      .subscribe();
  }

  login(username: string, password: string): Observable<void> {
    return this.http.post<{ token: string }>('/api/auth/token/', { username, password }).pipe(
      tap(({ token }) => {
        localStorage.setItem(TOKEN_KEY, token);
        // Gap 42 — anchor the countdown.
        this.markTokenRefreshed();
      }),
      switchMap(() => this.http.get<AuthUser>('/api/auth/me/')),
      tap(user => this.currentUserSub.next(user)),
      map(() => void 0)
    );
  }

  logout(): void {
    this.http.post('/api/auth/logout/', {}).subscribe({
      error: () => {
        console.warn('Server-side logout failed — token may still be valid on the server.');
      }
    });
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_ISSUED_AT_KEY);
    this.currentUserSub.next(null);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  /**
   * Phase E2 / Gap 42 — stamp "token is fresh as of now."
   *
   * Called by the login flow and by `SessionTimeoutService.extend()` when
   * the user clicks "Stay signed in" (or any keystroke extends the session
   * silently). SessionTimeoutService subtracts this from `Date.now()` to
   * decide whether to raise the warning dialog.
   */
  markTokenRefreshed(): void {
    try {
      localStorage.setItem(TOKEN_ISSUED_AT_KEY, Date.now().toString());
    } catch {
      // Private mode / quota — silent no-op; warning will still fire
      // at the default window from app start.
    }
  }

  /**
   * Phase E2 / Gap 42 — read the token-issued timestamp (ms since epoch).
   * Returns null if we have no record. Falsy values (0, NaN, negative) are
   * treated as "unknown" so the caller falls back to a safe default.
   */
  getTokenIssuedAt(): number | null {
    try {
      const raw = localStorage.getItem(TOKEN_ISSUED_AT_KEY);
      if (!raw) return null;
      const n = Number.parseInt(raw, 10);
      return Number.isFinite(n) && n > 0 ? n : null;
    } catch {
      return null;
    }
  }
}
