import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';

import { AuthService } from './auth.service';

export interface SessionReauthResult {
  success: boolean;
}

/**
 * Phase U1 / Gap 14 — re-auth dialog.
 *
 * Minimal, focused, no route change. Pre-fills the username from the
 * last-known session so the user only types a password. On success the
 * AuthService writes the new token to localStorage — the original
 * failing request can be retried from wherever it lives.
 */
@Component({
  selector: 'app-session-reauth-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatIconModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon aria-hidden="true" class="title-icon">lock_clock</mat-icon>
      Your session expired
    </h2>
    <mat-dialog-content>
      <p class="dialog-intro">
        Your sign-in timed out. Please enter your credentials to keep
        working — your current page state will be preserved.
      </p>

      @if (errorMessage) {
        <p class="dialog-error" role="alert">{{ errorMessage }}</p>
      }

      <mat-form-field appearance="outline" class="dialog-field">
        <mat-label>Username</mat-label>
        <input matInput
               type="text"
               autocomplete="username"
               [(ngModel)]="username"
               [disabled]="submitting"
               #usernameRef />
      </mat-form-field>

      <mat-form-field appearance="outline" class="dialog-field">
        <mat-label>Password</mat-label>
        <input matInput
               type="password"
               autocomplete="current-password"
               [(ngModel)]="password"
               [disabled]="submitting"
               (keydown.enter)="onSubmit()" />
      </mat-form-field>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button
              type="button"
              [disabled]="submitting"
              (click)="onCancel()">
        Sign out
      </button>
      <button mat-raised-button
              color="primary"
              type="button"
              [disabled]="submitting || !password"
              (click)="onSubmit()">
        @if (submitting) {
          <mat-spinner diameter="18" class="btn-spinner" />
        }
        Sign in
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon {
      vertical-align: middle;
      margin-right: 4px;
      color: var(--color-warning);
    }
    .dialog-intro {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 16px;
    }
    .dialog-error {
      font-size: 13px;
      color: var(--color-error-dark);
      background: var(--color-error-light);
      padding: 8px 12px;
      border-radius: 4px;
      margin: 0 0 16px;
    }
    .dialog-field {
      width: 100%;
      margin-bottom: 8px;
    }
    .btn-spinner {
      display: inline-block;
      margin-right: 8px;
    }
  `],
})
export class SessionReauthDialogComponent {
  private readonly auth = inject(AuthService);
  private readonly dialogRef = inject(MatDialogRef<SessionReauthDialogComponent, SessionReauthResult>);
  // Phase E2 / Gap 41 — cancel pending login if dialog is dismissed mid-submit.
  private readonly destroyRef = inject(DestroyRef);

  username = this.readLastUsername();
  password = '';
  submitting = false;
  errorMessage = '';

  onSubmit(): void {
    if (this.submitting) return;
    if (!this.username || !this.password) {
      this.errorMessage = 'Username and password are required.';
      return;
    }
    this.errorMessage = '';
    this.submitting = true;

    this.auth.login(this.username, this.password)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.rememberUsername(this.username);
        this.submitting = false;
        this.dialogRef.close({ success: true });
      },
      error: () => {
        this.submitting = false;
        this.errorMessage = 'Sign-in failed. Check your password and try again.';
      },
    });
  }

  onCancel(): void {
    // User chose to sign out. Clear the stored token (if any) so we go
    // back to the login page cleanly via the interceptor fallback.
    this.auth.logout();
    this.dialogRef.close({ success: false });
  }

  private readLastUsername(): string {
    try {
      return localStorage.getItem('xfil_last_username') ?? '';
    } catch {
      return '';
    }
  }

  private rememberUsername(name: string): void {
    try {
      localStorage.setItem('xfil_last_username', name);
    } catch {
      // Private browsing mode etc. — silent no-op.
    }
  }
}
