import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription, catchError, of, switchMap, tap, timer } from 'rxjs';
import { VisibilityGateService } from '../util/visibility-gate.service';

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

const POLL_INTERVAL_MS = 30_000;

@Injectable({ providedIn: 'root' })
export class MaintenanceModeService {
  private readonly http = inject(HttpClient);
  private readonly visibilityGate = inject(VisibilityGateService);
  // DestroyRef is taken at class-field init time, which is an injection
  // context — safe to pass into `takeUntilDestroyed` below from outside
  // one. A root service's DestroyRef fires on app shutdown, which is the
  // right lifetime for this poll.
  private readonly destroyRef = inject(DestroyRef);

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

  private pollSub: Subscription | null = null;

  /**
   * Idempotent. Safe to call multiple times — the second call returns
   * without opening a second poll. Call once from `AppComponent.ngOnInit`
   * so the maintenance banner reflects backend state throughout the
   * session. The poll pauses while the tab is hidden or the user is
   * signed out. See docs/PERFORMANCE.md §13.
   */
  start(): void {
    if (this.pollSub) return;
    this.pollSub = this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(0, POLL_INTERVAL_MS).pipe(switchMap(() => this.refresh())),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe();
  }

  stop(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
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
