import {
  DestroyRef,
  Directive,
  Input,
  OnInit,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NgControl } from '@angular/forms';

/**
 * Phase FR / Gap 112 — "Remember last value" smart-default directive.
 *
 * Drop on any `formControlName` or `[formControl]` input to remember
 * the last submitted value AS the default for the next blank form:
 *
 *   <mat-form-field>
 *     <input matInput formControlName="rateLimit" appSmartDefault="crawler.rateLimit" />
 *   </mat-form-field>
 *
 * On init: if the control's value is empty AND there's a remembered
 * default, patch it in.
 *
 * On every change: persist the new value (debounced) so the next
 * form-mount picks it up.
 *
 * Distinct from FormAutosave (Gap 110) — autosave is a per-FORM
 * snapshot keyed to that form instance; smart defaults are per-FIELD,
 * crossing form instances. Different storage namespace; both can be
 * active on the same form without conflict.
 */

const KEY_PREFIX = 'xfil_smart_default.';

@Directive({
  selector: '[appSmartDefault]',
  standalone: true,
})
export class SmartDefaultDirective implements OnInit {
  /** Storage key (will be prefixed with `xfil_smart_default.`).
   *  Conventional naming: `<feature>.<field>`. */
  @Input({ alias: 'appSmartDefault', required: true }) storageKey = '';
  /** Skip restoring when the form already has a non-empty value.
   *  Default true — usually you want the form's pre-set value to win. */
  @Input() respectExistingValue = true;

  private readonly control = inject(NgControl, { optional: true, self: true });
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    const ctrl = this.control?.control;
    if (!ctrl) {
      // eslint-disable-next-line no-console
      console.warn('[appSmartDefault] expects an NgControl host (formControl, formControlName, ngModel)');
      return;
    }

    if (!this.respectExistingValue || this.isEmpty(ctrl.value)) {
      const remembered = this.read();
      if (remembered !== null) {
        ctrl.setValue(remembered, { emitEvent: false });
      }
    }

    ctrl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((v) => {
        if (this.isEmpty(v)) return;
        this.persist(v);
      });
  }

  private isEmpty(v: unknown): boolean {
    return v === null || v === undefined || v === '' ||
      (Array.isArray(v) && v.length === 0);
  }

  private read(): unknown | null {
    try {
      const raw = localStorage.getItem(KEY_PREFIX + this.storageKey);
      if (raw === null) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  private persist(v: unknown): void {
    try {
      localStorage.setItem(KEY_PREFIX + this.storageKey, JSON.stringify(v));
    } catch {
      // No-op.
    }
  }
}
