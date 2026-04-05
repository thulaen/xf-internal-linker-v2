import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap, catchError, of } from 'rxjs';

export interface UserProfile {
  username: string;
  email?: string;
  full_name?: string;
  is_authenticated: boolean;
  is_staff: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private http = inject(HttpClient);
  
  private userSub = new BehaviorSubject<UserProfile | null>(null);
  user$ = this.userSub.asObservable();

  constructor() {
    this.checkSession();
  }

  checkSession(): void {
    this.http.get<UserProfile>('/api/auth/me/')
      .pipe(
        tap(user => this.userSub.next(user)),
        catchError(() => {
          const guest: UserProfile = { username: 'Guest', is_authenticated: false, is_staff: false };
          this.userSub.next(guest);
          return of(guest);
        })
      )
      .subscribe();
  }

  logout(): void {
    this.http.post('/api/auth/logout/', {})
      .pipe(
        tap(() => {
          this.userSub.next({ username: 'Guest', is_authenticated: false, is_staff: false });
          window.location.href = '/';
        }),
        catchError(() => {
          window.location.href = '/';
          return of(null);
        })
      )
      .subscribe();
  }

  login(): void {
    // Django login URL
    window.location.href = `/admin/login/?next=${encodeURIComponent(window.location.pathname)}`;
  }
}
