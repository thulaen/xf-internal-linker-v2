import { Injectable, computed, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D3 — combined service for the three dashboard chrome toggles:
 *   - Gap 161 Safe Mode (read-only flag for troubleshooting)
 *   - Gap 167 Calm Mode (hides non-essential cards)
 *
 * (The Emergency Stop button — Gap 168 — is a one-shot action, not a
 * persistent mode, so it stays in EmergencyStopComponent rather than
 * being modeled as a service flag here.)
 *
 * Safe Mode:
 *   When ON, the dashboard shows a banner and write-action buttons
 *   should self-disable. Components opt in by reading `safe()`.
 *
 * Calm Mode:
 *   When ON, components flagged as "non-essential" hide themselves
 *   for focused operation. Components opt in by reading `calm()`.
 *
 * Both persist in localStorage. Reset on demand.
 */

const SAFE_KEY = 'xfil_safe_mode';
const CALM_KEY = 'xfil_calm_mode';

@Injectable({ providedIn: 'root' })
export class DashboardModesService {
  private readonly _safe = signal<boolean>(this.read(SAFE_KEY));
  private readonly _calm = signal<boolean>(this.read(CALM_KEY));

  readonly safe = this._safe.asReadonly();
  readonly safe$ = toObservable(this._safe);

  readonly calm = this._calm.asReadonly();
  readonly calm$ = toObservable(this._calm);

  /** Either mode active = the dashboard is in a non-default state. */
  readonly anyActive = computed(() => this._safe() || this._calm());

  toggleSafe(): void {
    this.setSafe(!this._safe());
  }

  setSafe(next: boolean): void {
    this._safe.set(next);
    this.persist(SAFE_KEY, next);
  }

  toggleCalm(): void {
    this.setCalm(!this._calm());
  }

  setCalm(next: boolean): void {
    this._calm.set(next);
    this.persist(CALM_KEY, next);
  }

  // ── helpers ────────────────────────────────────────────────────────

  private read(key: string): boolean {
    try {
      return localStorage.getItem(key) === '1';
    } catch {
      return false;
    }
  }

  private persist(key: string, on: boolean): void {
    try {
      localStorage.setItem(key, on ? '1' : '0');
    } catch {
      // In-memory only.
    }
  }
}
