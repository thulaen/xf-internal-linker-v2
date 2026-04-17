import {
  DestroyRef,
  Directive,
  EventEmitter,
  Input,
  OnInit,
  Output,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormGroupDirective, NgForm } from '@angular/forms';
import { debounceTime } from 'rxjs';

/**
 * Phase FR / Gap 110 — Form draft autosave directive.
 *
 * Drop on any `<form [formGroup]="myForm" [appFormAutosave]="'reviewer-notes'">`
 * (or template-driven `<form #f="ngForm" [appFormAutosave]="'…'">`)
 * to:
 *   - Snapshot the form's value to localStorage every 800ms after a
 *     change.
 *   - Restore the saved snapshot on init when one exists, EXCEPT
 *     when it's older than `maxAgeMs` (default 7 days) — protects
 *     the user from a year-old draft surfacing surprise data.
 *   - Clear the snapshot on successful submit (consumer calls
 *     `clearDraft()` from the parent component).
 *
 * Storage key is namespaced under `xfil_form_draft.<key>` so different
 * forms don't collide.
 *
 * Why a directive vs a service: the directive picks up the form's
 * valueChanges observable automatically and ties its lifecycle to the
 * form. A service would force every consumer to wire subscriptions
 * by hand.
 */

const KEY_PREFIX = 'xfil_form_draft.';
const DEFAULT_DEBOUNCE_MS = 800;
const DEFAULT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

interface DraftPayload {
  /** ISO timestamp of when the draft was saved. */
  savedAt: number;
  /** The serialised form value (whatever JSON.stringify produces). */
  value: unknown;
}

@Directive({
  selector: '[appFormAutosave]',
  standalone: true,
  exportAs: 'appFormAutosave',
})
export class FormAutosaveDirective implements OnInit {
  /** Storage key (will be prefixed with `xfil_form_draft.`). */
  @Input({ alias: 'appFormAutosave', required: true }) key = '';
  /** Milliseconds after the last change before saving. Default 800. */
  @Input() debounceMs: number = DEFAULT_DEBOUNCE_MS;
  /** Drafts older than this are ignored on restore. Default 7 days. */
  @Input() maxAgeMs: number = DEFAULT_MAX_AGE_MS;
  /** When false, auto-restore on init is suppressed. Useful for
   *  per-record forms where the parent decides whether to restore. */
  @Input() autoRestore = true;

  /** Emitted after a draft has been restored from storage so the
   *  parent can show a "draft restored" snackbar with an Undo. */
  @Output() draftRestored = new EventEmitter<unknown>();
  /** Emitted after each autosave write. */
  @Output() draftSaved = new EventEmitter<unknown>();

  private readonly destroyRef = inject(DestroyRef);
  private readonly fgDirective = inject(FormGroupDirective, { optional: true, self: true });
  private readonly ngForm = inject(NgForm, { optional: true, self: true });

  private readonly form = this.fgDirective?.form ?? this.ngForm?.form ?? null;

  ngOnInit(): void {
    if (!this.form) {
      // Without a form there's nothing to save. Console hint helps
      // catch the directive being applied to a non-form element.
      // eslint-disable-next-line no-console
      console.warn(
        '[appFormAutosave] no FormGroup or NgForm bound — directive is a no-op',
      );
      return;
    }
    if (this.autoRestore) {
      const restored = this.restore();
      if (restored !== null) {
        // patchValue (not setValue) so missing keys don't blow up.
        this.form.patchValue(restored as never);
        this.draftRestored.emit(restored);
      }
    }
    this.form.valueChanges
      .pipe(debounceTime(this.debounceMs), takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.save(value);
      });
  }

  /** Manually clear the saved draft. Call after successful submit. */
  clearDraft(): void {
    try {
      localStorage.removeItem(KEY_PREFIX + this.key);
    } catch {
      // No-op.
    }
  }

  // ── internals ──────────────────────────────────────────────────────

  private save(value: unknown): void {
    try {
      const payload: DraftPayload = { savedAt: Date.now(), value };
      localStorage.setItem(KEY_PREFIX + this.key, JSON.stringify(payload));
      this.draftSaved.emit(value);
    } catch {
      // Quota / private mode — skip silently.
    }
  }

  private restore(): unknown | null {
    try {
      const raw = localStorage.getItem(KEY_PREFIX + this.key);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as Partial<DraftPayload>;
      if (typeof parsed?.savedAt !== 'number') return null;
      if (Date.now() - parsed.savedAt > this.maxAgeMs) {
        // Stale — wipe it so we don't keep checking.
        localStorage.removeItem(KEY_PREFIX + this.key);
        return null;
      }
      return parsed.value ?? null;
    } catch {
      return null;
    }
  }
}
