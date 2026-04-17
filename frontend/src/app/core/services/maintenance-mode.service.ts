import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, of, tap } from 'rxjs';

/**
 * Phase MX3 / Gap 344 — Maintenance mode toggle.
 *
 * When enabled, the shell shows a persistent amber banner and all
 * write endpoints return 503 (backend enforcement lands in a future
 * middleware pass; this service covers the frontend half + polls the
 * flag every 30 s so any tab reflects a backend-initiated toggle).
 *
 * Backing store: the `system.maintenance_mode` AppSetting — matches
 * the convention of `system.master_pause`.
 */

export interface MaintenanceModeState {
  enabled: boolean;
  message: string;
  started_at: string | null;
}

@Injectable({ providedIn: 'root' })
export class MaintenanceModeService {
  private http = inject(HttpClient);

  private readonly _state = signal<MaintenanceModeState>({
    enabled: false,
    message: '',
    started_at: null,
  });

  readonly state = this._state.asReadonly();
  readonly enabled = computed(() => this._state().enabled);
  readonly bannerText = computed(() => {
    const s = this._state();
    if (!s.enabled) return '';
    return s.message || 'The system is in maintenance mode — writes are disabled.';
  });

  start(): void {
    this.refresh().subscribe();
    // 30 s poll — cheap, and maintenance mode toggles are rare.
    setInterval(() => this.refresh().subscribe(), 30_000);
  }

  refresh() {
    return this.http
      .get<MaintenanceModeState>('/api/settings/maintenance-mode/')
      .pipe(
        tap((s) => this._state.set(s)),
        catchError(() => of(this._state())),
      );
  }

  setEnabled(enabled: boolean, message = '') {
    return this.http
      .post<MaintenanceModeState>('/api/settings/maintenance-mode/', {
        enabled,
        message,
      })
      .pipe(tap((s) => this._state.set(s)));
  }
}
