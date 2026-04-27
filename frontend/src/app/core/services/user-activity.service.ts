import { DestroyRef, Injectable, NgZone, inject } from '@angular/core';
import { PerformanceModeService } from './performance-mode.service';

/**
 * Tracks keyboard / mouse activity at the window level.
 *
 * Plan item 13 ("Until I come back"): when the user picks that expiry chip
 * while High Performance mode is active, this service waits for at least
 * `IDLE_THRESHOLD_MS` of inactivity (so the user has genuinely walked away),
 * and the NEXT activity event after that triggers a call to the backend
 * /api/settings/runtime/activity-resumed/ endpoint. The backend flips the
 * mode back to Balanced and emits the perf-mode-reverted alert.
 *
 * Why debounce + idle-gate:
 *   - Without the idle gate, every mouse wiggle would ping the backend.
 *   - Without the resume-after-idle pattern, the user would have to be idle
 *     for a long time *before* the call fires, which feels wrong. "Until I
 *     come back" means "after I've stepped away and come back", so we need
 *     both the stepping-away check and the come-back signal.
 *
 * The service is instantiated once in AppComponent and self-cleans on destroy.
 */
@Injectable({ providedIn: 'root' })
export class UserActivityService {
  /** Time without any keyboard/mouse events before we consider the user "away". */
  private static readonly IDLE_THRESHOLD_MS = 60_000; // 60 s

  /** Rate-limit the activity-resumed API call so we don't hammer the backend. */
  private static readonly RESUME_CALL_COOLDOWN_MS = 30_000; // 30 s

  private readonly perfMode = inject(PerformanceModeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly zone = inject(NgZone);

  private lastActivityAt = Date.now();
  private lastResumeCallAt = 0;
  private started = false;

  private readonly handler = (): void => {
    const now = Date.now();
    const wasAway = now - this.lastActivityAt >= UserActivityService.IDLE_THRESHOLD_MS;
    this.lastActivityAt = now;

    if (!wasAway) return;

    // Only ping the backend when the user set "Until I come back" AND mode is high.
    if (this.perfMode.mode() !== 'high' || this.perfMode.expiry() !== 'activity') return;

    if (now - this.lastResumeCallAt < UserActivityService.RESUME_CALL_COOLDOWN_MS) return;
    this.lastResumeCallAt = now;

    this.perfMode.notifyActivityResumed().subscribe();
  };

  /** Start listening. Safe to call multiple times — no-op after the first. */
  start(): void {
    if (this.started || typeof window === 'undefined') return;
    this.started = true;
    // Listen outside Angular's zone — every mouse wiggle / keypress would
    // otherwise re-trigger global change detection. The handler debounces
    // and only re-enters the zone via perfMode.notifyActivityResumed() (an
    // RxJS Observable that ticks zone-aware HTTP), so OnPush trees stay calm.
    this.zone.runOutsideAngular(() => {
      window.addEventListener('mousemove', this.handler, { passive: true });
      window.addEventListener('keydown', this.handler, { passive: true });
      window.addEventListener('touchstart', this.handler, { passive: true });
    });

    this.destroyRef.onDestroy(() => this.stop());
  }

  /** Stop listening. Idempotent. */
  stop(): void {
    if (!this.started || typeof window === 'undefined') return;
    window.removeEventListener('mousemove', this.handler);
    window.removeEventListener('keydown', this.handler);
    window.removeEventListener('touchstart', this.handler);
    this.started = false;
  }
}
