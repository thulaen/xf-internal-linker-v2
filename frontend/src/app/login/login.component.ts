import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { filter, take } from 'rxjs';
import { AuthService } from '../core/services/auth.service';
import { PasskeyService } from '../core/services/passkey.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);
  private passkey = inject(PasskeyService);

  /** Phase F1 / Gap 95 — passkey availability. The button shows only
   *  when the browser supports WebAuthn AND the server's passkey
   *  endpoints respond (HEAD probe). */
  readonly passkeyAvailable = signal(false);
  readonly passkeyBusy = signal(false);

  // ReactiveForms manages its own change detection internally — keep
  // the FormGroup as a plain field. Templates read `form.controls.X`
  // directly; ReactiveForms emits status/value changes through its
  // own observables, which trigger CD on the host component.
  readonly form = new FormGroup({
    username: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  // Render-affecting state in signals so OnPush picks up loading-spinner
  // and error-message changes without markForCheck.
  readonly loading = signal(false);
  readonly errorMessage = signal('');
  private returnUrl = '/';

  ngOnInit(): void {
    this.returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/';

    // Phase F1 / Gap 95 — detect passkey availability.
    void this.passkey.isAvailable().then((avail) => this.passkeyAvailable.set(avail));

    // Redirect already-authenticated users away from login page
    this.auth.isChecking$.pipe(
      filter(checking => !checking),
      take(1),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(() => {
      this.auth.isLoggedIn$.pipe(take(1)).subscribe(loggedIn => {
        if (loggedIn) {
          this.router.navigateByUrl(this.returnUrl || '/dashboard');
        }
      });
    });
  }

  submit(): void {
    if (this.form.invalid || this.loading()) return;

    this.loading.set(true);
    this.errorMessage.set('');

    const { username, password } = this.form.getRawValue();
    this.auth.login(username, password)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => this.router.navigateByUrl(this.returnUrl),
      error: (err: HttpErrorResponse) => {
        this.errorMessage.set(this.getErrorMessage(err));
        this.loading.set(false);
      },
    });
  }

  /** Phase F1 / Gap 95 — passkey sign-in handler. */
  async loginWithPasskey(): Promise<void> {
    if (this.passkeyBusy()) return;
    this.passkeyBusy.set(true);
    this.errorMessage.set('');
    const result = await this.passkey.login();
    this.passkeyBusy.set(false);
    if (result.ok) {
      this.router.navigateByUrl(this.returnUrl || '/dashboard');
      return;
    }
    if (result.reason === 'cancelled') return; // user pressed cancel
    if (result.reason === 'unsupported') {
      this.errorMessage.set('Your browser does not support passkeys.');
      return;
    }
    if (result.reason === 'not-configured') {
      this.errorMessage.set('Passkey sign-in is not yet configured on this server.');
      return;
    }
    this.errorMessage.set(result.detail || 'Passkey sign-in failed.');
  }

  private getErrorMessage(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return 'Cannot reach the server. Check your connection.';
    }
    if (err.status === 401 || err.status === 400) {
      return 'Invalid username or password.';
    }
    if (err.status === 429) {
      return 'Too many login attempts. Please wait a moment.';
    }
    if (err.status >= 500) {
      return 'Server error. Please try again later.';
    }
    return 'Login failed. Please try again.';
  }
}
