import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, of, tap } from 'rxjs';

/**
 * Shared state for the current Performance Mode and its auto-revert expiry.
 *
 * Backing signals are read by:
 *   - the Dashboard's Performance Mode card (source of truth for clicks + chips)
 *   - the global toolbar chip (lets the user see the active mode from any page)
 *   - the UserActivityService (to know whether to call /activity-resumed/)
 *
 * Server side is the source of truth; this service calls `/api/settings/runtime/`
 * on boot and after every switch so the UI and backend stay in sync.
 */
export type PerformanceExpiry = 'none' | 'activity' | 'night';

export interface RuntimeSettingsResponse {
  runtime_mode: string;
  performance_mode: string;
  effective_runtime_mode?: string;
  performance_mode_expiry?: PerformanceExpiry;
  performance_mode_expires_at?: string;
}

@Injectable({ providedIn: 'root' })
export class PerformanceModeService {
  private http = inject(HttpClient);

  private readonly _mode = signal<string>('balanced');
  private readonly _expiry = signal<PerformanceExpiry>('none');
  private readonly _expiresAt = signal<string>('');

  readonly mode = this._mode.asReadonly();
  readonly expiry = this._expiry.asReadonly();
  readonly expiresAt = this._expiresAt.asReadonly();

  readonly label = computed(() => {
    switch (this._mode()) {
      case 'safe':
        return 'Safe';
      case 'high':
        return 'High Performance';
      default:
        return 'Balanced';
    }
  });

  readonly icon = computed(() => {
    switch (this._mode()) {
      case 'safe':
        return 'shield';
      case 'high':
        return 'speed';
      default:
        return 'balance';
    }
  });

  /** Fetch the current mode + expiry from the backend and publish. */
  refresh(): Observable<RuntimeSettingsResponse> {
    return this.http
      .get<RuntimeSettingsResponse>('/api/settings/runtime/')
      .pipe(
        tap((rt) => {
          this._mode.set(rt.performance_mode || 'balanced');
          this._expiry.set(rt.performance_mode_expiry ?? 'none');
          this._expiresAt.set(rt.performance_mode_expires_at ?? '');
        }),
        catchError(() =>
          of<RuntimeSettingsResponse>({
            runtime_mode: 'cpu',
            performance_mode: this._mode(),
            effective_runtime_mode: 'cpu',
            performance_mode_expiry: this._expiry(),
            performance_mode_expires_at: this._expiresAt(),
          }),
        ),
      );
  }

  /** Called by the Dashboard card after a successful local switch (optimistic). */
  setMode(mode: string): void {
    this._mode.set(mode);
  }

  /**
   * Persist a mode + optional expiry to the backend.
   * Returns the server's authoritative response so callers can sync.
   */
  switchMode(
    mode: string,
    expiry: PerformanceExpiry = 'none',
    expiresAt: string = '',
  ): Observable<RuntimeSettingsResponse> {
    const body: Record<string, string> = { mode };
    if (mode === 'high' && expiry !== 'none') {
      body['expiry'] = expiry;
      if (expiresAt) body['expires_at'] = expiresAt;
    }
    return this.http
      .post<RuntimeSettingsResponse>('/api/settings/runtime/switch/', body)
      .pipe(
        tap((rt) => {
          this._mode.set(rt.performance_mode || mode);
          this._expiry.set(rt.performance_mode_expiry ?? 'none');
          this._expiresAt.set(rt.performance_mode_expires_at ?? '');
        }),
      );
  }

  /** Update only the expiry selection (mode stays at whatever it is). */
  setExpiry(expiry: PerformanceExpiry, expiresAt: string = ''): Observable<RuntimeSettingsResponse> {
    return this.switchMode(this._mode(), expiry, expiresAt);
  }

  /**
   * Called by UserActivityService when keyboard/mouse activity resumes while
   * mode is 'high' + expiry 'activity'. Best-effort — backend decides whether
   * the revert actually fires.
   */
  notifyActivityResumed(): Observable<{ reverted: boolean; reason?: string }> {
    return this.http
      .post<{ reverted: boolean; reason?: string }>(
        '/api/settings/runtime/activity-resumed/',
        {},
      )
      .pipe(
        tap((res) => {
          if (res.reverted) {
            this._mode.set('balanced');
            this._expiry.set('none');
            this._expiresAt.set('');
          }
        }),
        catchError(() => of({ reverted: false })),
      );
  }
}
