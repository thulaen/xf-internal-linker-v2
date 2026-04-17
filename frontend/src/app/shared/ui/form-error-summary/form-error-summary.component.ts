import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { AbstractControl, FormGroup, ValidationErrors } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase FR / Gap 111 — Form error summary card.
 *
 * Renders ABOVE a form. When the user hits Submit on an invalid form,
 * this component lists every field error with an anchor link that
 * scrolls + focuses the broken field.
 *
 * Usage:
 *
 *   <app-form-error-summary
 *     [form]="myForm"
 *     [show]="submitted && myForm.invalid"
 *     [labels]="fieldLabels"
 *   />
 *
 *   <form [formGroup]="myForm" (ngSubmit)="onSubmit()">
 *     <mat-form-field>
 *       <input matInput formControlName="email" id="field-email" />
 *     </mat-form-field>
 *     ...
 *   </form>
 *
 * The anchor target is `#field-<controlName>` by default. Consumers
 * can override per-field with the `anchorIds` input.
 *
 * Why this matters: WCAG 3.3.1 (Error Identification) requires errors
 * be identified in text near the form. Material's per-field mat-error
 * satisfies that, but for long forms a summary at the top is the
 * faster path for keyboard + screen-reader users.
 */
@Component({
  selector: 'app-form-error-summary',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule],
  template: `
    @if (show && entries().length > 0) {
      <aside
        class="fes"
        role="alert"
        aria-live="assertive"
        tabindex="-1"
      >
        <header class="fes-head">
          <mat-icon class="fes-icon" aria-hidden="true">error</mat-icon>
          <h3 class="fes-title">
            {{ entries().length }} field{{ entries().length === 1 ? ' has' : 's have' }} a problem
          </h3>
        </header>
        <ul class="fes-list">
          @for (e of entries(); track e.field) {
            <li>
              <a [href]="'#' + e.anchorId" (click)="onJump($event, e.anchorId)">
                <strong>{{ e.label }}:</strong> {{ e.message }}
              </a>
            </li>
          }
        </ul>
      </aside>
    }
  `,
  styles: [`
    .fes {
      padding: 12px 16px;
      margin-bottom: 16px;
      border: var(--card-border);
      border-left: 4px solid var(--color-error, #d93025);
      background: var(--color-error-50, rgba(217, 48, 37, 0.06));
      border-radius: var(--card-border-radius, 8px);
    }
    .fes-head {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
    }
    .fes-icon { color: var(--color-error, #d93025); }
    .fes-title {
      margin: 0;
      font-size: 14px;
      font-weight: 500;
      color: var(--color-error-dark, #b3261e);
    }
    .fes-list {
      list-style: disc inside;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .fes-list a {
      color: var(--color-error-dark, #b3261e);
      text-decoration: underline;
      font-size: 13px;
      line-height: 1.5;
    }
    .fes-list a:hover { text-decoration: none; }
  `],
})
export class FormErrorSummaryComponent {
  /** Reactive form to scan. */
  @Input({ required: true }) set form(value: FormGroup) {
    this._form.set(value);
  }
  /** Show / hide the summary. Parent typically toggles after submit. */
  @Input() show = false;
  /** Friendly labels keyed by control name (e.g. {email: 'Email address'}). */
  @Input() labels: Readonly<Record<string, string>> = {};
  /** Override anchor ids per control. Default: `field-<controlName>`. */
  @Input() anchorIds: Readonly<Record<string, string>> = {};
  /** Custom message-per-error-key. Defaults below cover the common ones. */
  @Input() messages: Readonly<Record<string, string>> = {};

  private readonly _form = signal<FormGroup | null>(null);

  readonly entries = computed(() => {
    const form = this._form();
    if (!form) return [];
    const out: { field: string; label: string; message: string; anchorId: string }[] = [];
    for (const [name, ctrl] of Object.entries(form.controls)) {
      if (!ctrl || ctrl.valid || ctrl.disabled) continue;
      const errors = (ctrl as AbstractControl).errors as ValidationErrors | null;
      if (!errors) continue;
      out.push({
        field: name,
        label: this.labels[name] ?? this.humanise(name),
        message: this.firstMessage(name, errors),
        anchorId: this.anchorIds[name] ?? `field-${name}`,
      });
    }
    return out;
  });

  onJump(event: Event, anchorId: string): void {
    event.preventDefault();
    const el = document.getElementById(anchorId);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // Focus is the actually-useful behaviour for screen readers; only
    // do it for focusable elements to avoid nudging things like
    // mat-radio-group containers.
    if (
      el instanceof HTMLInputElement ||
      el instanceof HTMLTextAreaElement ||
      el instanceof HTMLSelectElement ||
      el.tabIndex >= 0
    ) {
      try { el.focus({ preventScroll: true }); } catch { /* no-op */ }
    }
  }

  private firstMessage(name: string, errors: ValidationErrors): string {
    const keys = Object.keys(errors);
    if (keys.length === 0) return 'is invalid';
    const key = keys[0];
    if (this.messages[key]) return this.messages[key];
    return DEFAULT_MESSAGES[key] ?? `${this.humanise(name)} is invalid`;
  }

  private humanise(name: string): string {
    return name
      .replace(/([A-Z])/g, ' $1')
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/^./, (c) => c.toUpperCase());
  }
}

const DEFAULT_MESSAGES: Record<string, string> = {
  required: 'is required',
  email: 'must be a valid email address',
  minlength: 'is too short',
  maxlength: 'is too long',
  min: 'is too small',
  max: 'is too large',
  pattern: 'is not in the expected format',
};
