import { Component, DestroyRef, inject, OnInit } from '@angular/core';
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
})
export class LoginComponent implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);

  form = new FormGroup({
    username: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  loading = false;
  errorMessage = '';
  private returnUrl = '/';

  ngOnInit(): void {
    this.returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/';

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
    if (this.form.invalid || this.loading) return;

    this.loading = true;
    this.errorMessage = '';

    const { username, password } = this.form.getRawValue();
    this.auth.login(username, password).subscribe({
      next: () => this.router.navigateByUrl(this.returnUrl),
      error: (err: HttpErrorResponse) => {
        this.errorMessage = this.getErrorMessage(err);
        this.loading = false;
      },
    });
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
