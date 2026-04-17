import { Injectable, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D3 / Gap 177 — FAQ drawer open/close service.
 *
 * Same shape as GlossaryService: a single signal holds the drawer's
 * open state, the toolbar 💬 button calls `toggle()`, and the
 * FaqDrawerComponent renders based on `open()`.
 */
@Injectable({ providedIn: 'root' })
export class FaqService {
  private readonly _open = signal(false);

  readonly open = this._open.asReadonly();
  readonly open$ = toObservable(this._open);

  toggle(): void {
    this._open.set(!this._open());
  }

  openDrawer(): void {
    this._open.set(true);
  }

  closeDrawer(): void {
    this._open.set(false);
  }
}
