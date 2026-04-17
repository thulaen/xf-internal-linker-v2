import { Component, ChangeDetectionStrategy, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { toSignal } from '@angular/core/rxjs-interop';
import { fromEvent, merge, map, startWith } from 'rxjs';

/**
 * Phase U1 / Gap 11 — Persistent top banner shown when the browser
 * loses its network connection, auto-hides when connectivity returns.
 *
 * Listens to the window `online` / `offline` events and uses the
 * initial `navigator.onLine` value so a user who opens an already-
 * disconnected browser tab sees the banner straight away.
 *
 * Accessibility:
 *   - `role="alert"` so screen readers announce the state change.
 *   - `aria-live="polite"` (implicit via `role="alert"`) keeps the
 *     announcement non-blocking.
 *
 * Styling lives in the component's own SCSS — banner spans the page,
 * uses `var(--color-warning)` as the background, white text. Floats
 * at top of the main content so it doesn't shift the layout (fixed
 * position above the content, content gets a matching top offset via
 * `--offline-banner-offset` on the :root element when the banner is
 * showing).
 */
@Component({
  selector: 'app-offline-banner',
  standalone: true,
  imports: [CommonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!online()) {
      <div class="offline-banner" role="alert">
        <mat-icon aria-hidden="true">cloud_off</mat-icon>
        <span class="offline-text">
          <strong>You're offline.</strong>
          Changes may not save until connection returns.
        </span>
      </div>
    }
  `,
  styleUrls: ['./offline-banner.component.scss'],
})
export class OfflineBannerComponent {
  private readonly destroyRef = inject(DestroyRef);

  /**
   * Signal reflecting the current online state. `true` when the
   * browser reports a network connection, `false` during an outage.
   *
   * Uses `toSignal` so the template reads as `online()` and Angular's
   * zone-less change detection (when enabled) picks up updates
   * automatically. `startWith(navigator.onLine)` seeds the signal so
   * a freshly-opened offline tab shows the banner immediately.
   */
  readonly online = toSignal(
    merge(
      fromEvent(window, 'online').pipe(map(() => true)),
      fromEvent(window, 'offline').pipe(map(() => false)),
    ).pipe(startWith(navigator.onLine)),
    { initialValue: navigator.onLine },
  );
}
