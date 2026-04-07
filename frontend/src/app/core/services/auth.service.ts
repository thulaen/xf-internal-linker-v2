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
        }),
        catchError(() => {
          localStorage.removeItem(TOKEN_KEY);
          this.currentUserSub.next(null);
          this.checkingSub.next(false);
          return of(null);
        })
      )
      .subscribe();
  }

  login(username: string, password: string): Observable<void> {
    return this.http.post<{ token: string }>('/api/auth/token/', { username, password }).pipe(
      tap(({ token }) => localStorage.setItem(TOKEN_KEY, token)),
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
    this.currentUserSub.next(null);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }
}
