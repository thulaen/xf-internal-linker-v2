import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, of, tap } from 'rxjs';

/**
 * Shared state for the current Performance Mode.
 *
 * Backing signal is read by:
 *   - the Dashboard's Performance Mode card (source of truth for clicks)
 *   - the global toolbar chip (lets the user see the active mode from any page)
 *
 * Keeps both in sync without polling: the card calls setMode() after a
 * successful switch, and the chip updates immediately via the signal.
 */
@Injectable({ providedIn: 'root' })
export class PerformanceModeService {
  private http = inject(HttpClient);

  private readonly _mode = signal<string>('balanced');
  readonly mode = this._mode.asReadonly();

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

  /** Fetch the mode from the backend and publish it. */
  refresh() {
    return this.http
      .get<{ runtime_mode: string; performance_mode: string }>('/api/settings/runtime/')
      .pipe(
        tap((rt) => this._mode.set(rt.performance_mode || 'balanced')),
        catchError(() => of({ runtime_mode: 'cpu', performance_mode: this._mode() })),
      );
  }

  /** Called by the Dashboard card after a successful switch. */
  setMode(mode: string): void {
    this._mode.set(mode);
  }
}
