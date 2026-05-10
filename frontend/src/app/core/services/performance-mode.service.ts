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
  // Hardware capability gate (added 2026-05-09 per AutoIssue #16). The
  // backend's `_runtime_settings_snapshot()` now includes the detected
  // hardware tier + a flag saying whether the machine can actually run
  // High Performance (CUDA + ≥4 GB VRAM). The card reads these to
  // disable the High button on CPU-only / low-VRAM machines instead of
  // letting the user pick High and silently fall back at runtime.
  hardware_tier?: 'low' | 'medium' | 'high' | 'workstation';
  high_performance_capable?: boolean;
  hardware_summary?: string;
}

@Injectable({ providedIn: 'root' })
export class PerformanceModeService {
  private http = inject(HttpClient);

  private readonly _mode = signal<string>('balanced');
  private readonly _expiry = signal<PerformanceExpiry>('none');
  private readonly _expiresAt = signal<string>('');
  private readonly _highCapable = signal<boolean>(true);
  private readonly _hardwareTier = signal<string>('high');
  private readonly _hardwareSummary = signal<string>('');

  readonly mode = this._mode.asReadonly();
  readonly expiry = this._expiry.asReadonly();
  readonly expiresAt = this._expiresAt.asReadonly();
  readonly highPerformanceCapable = this._highCapable.asReadonly();
  readonly hardwareTier = this._hardwareTier.asReadonly();
  readonly hardwareSummary = this._hardwareSummary.asReadonly();

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
          if (rt.high_performance_capable !== undefined) {
            this._highCapable.set(rt.high_performance_capable);
          }
          if (rt.hardware_tier !== undefined) {
            this._hardwareTier.set(rt.hardware_tier);
          }
          if (rt.hardware_summary !== undefined) {
            this._hardwareSummary.set(rt.hardware_summary);
          }
        }),
        catchError(() =>
          of<RuntimeSettingsResponse>({
            runtime_mode: 'cpu',
            performance_mode: this._mode(),
            effective_runtime_mode: 'cpu',
            performance_mode_expiry: this._expiry(),
            performance_mode_expires_at: this._expiresAt(),
            high_performance_capable: this._highCapable(),
            hardware_tier: this._hardwareTier() as 'low' | 'medium' | 'high' | 'workstation',
            hardware_summary: this._hardwareSummary(),
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
