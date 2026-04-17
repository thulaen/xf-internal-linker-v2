import { Injectable, computed, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { inject } from '@angular/core';

/**
 * Phase MX3 / Gap 343 — Dry-run / simulate mode.
 *
 * Session-scoped flag plus a global HTTP interceptor (wired separately
 * in `app.config.ts`) that stamps `X-Dry-Run: 1` on outbound POST /
 * PATCH / DELETE requests when enabled. The backend middleware returns
 * a synthesised response without writing.
 *
 * Banner is rendered by `app.component` on top of the shell so the
 * operator can't forget they're in simulate mode.
 */

const STORAGE_KEY = 'dryrun.enabled';

@Injectable({ providedIn: 'root' })
export class DryRunService {
  private doc = inject(DOCUMENT);

  private readonly _enabled = signal<boolean>(this.read());
  readonly enabled = this._enabled.asReadonly();
  readonly bannerText = computed(() =>
    this._enabled()
      ? 'Dry-run mode ON — writes are simulated, not persisted.'
      : '',
  );

  toggle(): void {
    this._enabled.set(!this._enabled());
    this.persist();
  }

  set(value: boolean): void {
    this._enabled.set(!!value);
    this.persist();
  }

  private persist(): void {
    try {
      this.doc.defaultView?.localStorage.setItem(
        STORAGE_KEY,
        this._enabled() ? '1' : '0',
      );
    } catch {
      /* private mode — in-memory only */
    }
  }

  private read(): boolean {
    try {
      return this.doc.defaultView?.localStorage.getItem(STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  }
}
