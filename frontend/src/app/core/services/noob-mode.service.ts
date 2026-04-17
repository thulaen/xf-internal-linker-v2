import { Injectable, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase D2 / Gap 71 — Noob / Pro mode service.
 *
 * Two-state global toggle that lets components decide whether to show
 * advanced knobs. Defaults to NOOB on first visit so the dashboard
 * is approachable; experienced operators flip it to PRO once they
 * know what they're doing.
 *
 * Components opt in by reading the signal:
 *
 *   @Component({ ... })
 *   export class WeightTunerComponent {
 *     private readonly mode = inject(NoobModeService);
 *     showAdvanced = computed(() => this.mode.mode() === 'pro');
 *   }
 *
 *   <ng-container *ngIf="showAdvanced()">
 *     <!-- Pro-only sliders -->
 *   </ng-container>
 *
 * Distinct from Tutorial Mode (Gap 55, callouts) and Explain Mode
 * (Gap 58, info icons). Those add INSTRUCTIONAL ui; Noob Mode HIDES
 * complexity entirely.
 */

export type OperatorMode = 'noob' | 'pro';

const KEY = 'xfil_operator_mode';

@Injectable({ providedIn: 'root' })
export class NoobModeService {
  private readonly _mode = signal<OperatorMode>(this.read());

  readonly mode = this._mode.asReadonly();
  readonly mode$ = toObservable(this._mode);

  toggle(): void {
    this.setMode(this._mode() === 'noob' ? 'pro' : 'noob');
  }

  setMode(next: OperatorMode): void {
    this._mode.set(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // In-memory only.
    }
  }

  private read(): OperatorMode {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw === 'pro') return 'pro';
      return 'noob';
    } catch {
      return 'noob';
    }
  }
}
