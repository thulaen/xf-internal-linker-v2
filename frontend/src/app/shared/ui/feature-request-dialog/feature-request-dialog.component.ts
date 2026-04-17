import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FeatureRequestPriority,
  FeatureRequestService,
} from '../../../core/services/feature-request.service';

/**
 * Phase GB / Gap 151 — "Suggest a feature" dialog.
 *
 * Single Material dialog the toolbar trigger opens. Captures:
 *   • title     — short headline (required)
 *   • body      — long-form pitch (≥10 chars)
 *   • category  — optional tag for triage (UI / backend / data / …)
 *   • priority  — self-declared urgency (low / medium / high)
 *
 * On submit, the service captures the route, locale, viewport, and
 * timezone automatically; the user doesn't have to think about it.
 * On success: snackbar confirmation + dialog closes. On error: inline
 * banner; dialog stays open so the user doesn't lose their draft.
 */
@Component({
  selector: 'app-feature-request-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatIconModule,
  ],
  template: `
    <h2 mat-dialog-title>Suggest a feature</h2>
    <mat-dialog-content>
      <p class="fr-hint">
        We read every submission. Please describe the outcome you want and,
        if helpful, what you'd click to get there.
      </p>

      @if (errorMsg()) {
        <div class="fr-error" role="alert">
          <mat-icon>error_outline</mat-icon>
          <span>{{ errorMsg() }}</span>
        </div>
      }

      <form [formGroup]="form" class="fr-form" (ngSubmit)="submit()">
        <mat-form-field appearance="outline">
          <mat-label>Headline</mat-label>
          <input
            matInput
            formControlName="title"
            maxlength="160"
            autocomplete="off"
            placeholder="Short one-line summary"
            required
          />
          @if (form.controls.title.touched && form.controls.title.hasError('required')) {
            <mat-error>Please give it a short headline.</mat-error>
          }
          @if (form.controls.title.touched && form.controls.title.hasError('minlength')) {
            <mat-error>A few more characters, please.</mat-error>
          }
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Describe it</mat-label>
          <textarea
            matInput
            rows="6"
            formControlName="body"
            maxlength="10000"
            placeholder="What should it do? Why does it matter? What would you click?"
            required
          ></textarea>
          @if (form.controls.body.touched && form.controls.body.hasError('minlength')) {
            <mat-error>Please describe it in at least 10 characters.</mat-error>
          }
        </mat-form-field>

        <div class="fr-row">
          <mat-form-field appearance="outline" class="fr-cat">
            <mat-label>Area (optional)</mat-label>
            <mat-select formControlName="category">
              <mat-option value="">Unsure</mat-option>
              <mat-option value="ui">UI / UX</mat-option>
              <mat-option value="dashboard">Dashboard</mat-option>
              <mat-option value="review">Review / Suggestions</mat-option>
              <mat-option value="analytics">Analytics</mat-option>
              <mat-option value="settings">Settings</mat-option>
              <mat-option value="performance">Performance</mat-option>
              <mat-option value="backend">Backend / pipeline</mat-option>
              <mat-option value="other">Other</mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="fr-pri">
            <mat-label>Urgency</mat-label>
            <mat-select formControlName="priority">
              <mat-option value="low">Low — nice to have</mat-option>
              <mat-option value="medium">Medium — would help</mat-option>
              <mat-option value="high">High — blocks me</mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </form>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="close()" [disabled]="submitting()">
        Cancel
      </button>
      <button
        mat-raised-button
        color="primary"
        type="button"
        (click)="submit()"
        [disabled]="submitting() || form.invalid"
      >
        @if (submitting()) {
          Sending…
        } @else {
          Send it
        }
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; min-width: 480px; }
    .fr-hint {
      margin: 0 0 16px;
      font-size: 13px;
      color: var(--color-text-secondary, #5f6368);
    }
    .fr-form {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .fr-row {
      display: flex;
      gap: 16px;
    }
    .fr-cat { flex: 2; }
    .fr-pri { flex: 1; }
    mat-form-field { width: 100%; }
    .fr-error {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 4px;
      margin-bottom: 12px;
      background: var(--color-bg-faint, #fce8e6);
      color: var(--color-error, #d93025);
      font-size: 13px;
    }
  `],
})
export class FeatureRequestDialogComponent {
  private fb = inject(FormBuilder);
  private service = inject(FeatureRequestService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);
  private dialogRef =
    inject<MatDialogRef<FeatureRequestDialogComponent>>(MatDialogRef);

  readonly submitting = signal(false);
  readonly errorMsg = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.minLength(3)]],
    body: ['', [Validators.required, Validators.minLength(10)]],
    category: [''],
    priority: ['medium' as FeatureRequestPriority],
  });

  submit(): void {
    this.errorMsg.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    const v = this.form.getRawValue();
    this.service
      .submit({
        title: v.title.trim(),
        body: v.body.trim(),
        category: v.category.trim(),
        priority: v.priority,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.snack.open('Feature request sent — thank you!', 'OK', {
            duration: 4000,
          });
          this.dialogRef.close(true);
        },
        error: (err: unknown) => {
          this.submitting.set(false);
          this.errorMsg.set(this.explain(err));
        },
      });
  }

  close(): void {
    this.dialogRef.close(false);
  }

  private explain(err: unknown): string {
    if (!err || typeof err !== 'object') return 'Could not send. Please try again.';
    const e = err as { status?: number; error?: { detail?: string } };
    if (e.status === 429) return 'Too many submissions this hour. Please try later.';
    if (e.status === 401) return 'Session expired. Please sign in and try again.';
    if (e.status === 400 && e.error?.detail) return e.error.detail;
    return 'Could not send. Please try again.';
  }
}
