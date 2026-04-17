import { Injectable, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D2 / Gap 69 — Glossary drawer open/close service.
 *
 * Single signal holding the drawer's open state. AppComponent
 * subscribes via the observable form to drive a `<mat-sidenav>`-style
 * panel; the global ALT+G keyboard handler in AppComponent calls
 * `toggle()` to flip it.
 *
 * Stateless beyond open/closed — the actual term list is in
 * `glossary.data.ts` and rendered by `GlossaryDrawerComponent`.
 */
@Injectable({ providedIn: 'root' })
export class GlossaryService {
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
