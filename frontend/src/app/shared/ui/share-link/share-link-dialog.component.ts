import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatOptionModule } from '@angular/material/core';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, of } from 'rxjs';

export interface ShareLinkDialogData {
  /** Human label shown in the title ("Share suggestion", "Share report"). */
  title: string;
  /** Target type + id serialised to the server. */
  targetType: string;
  targetId: string | number;
}

export interface ShareLinkResponse {
  url: string;
  expires_at: string;
}

/**
 * Phase DC / Gap 127 — Share-link dialog.
 *
 * POSTs to `/api/share-links/` (future endpoint) with
 * { target_type, target_id, expires_in_seconds } and receives a
 * signed read-only URL + expiry timestamp. The dialog shows the
 * URL in a read-only field with a Copy button.
 *
 * Until the backend endpoint ships, the dialog surfaces a clear
 * "not configured" message rather than silently breaking.
 */
@Component({
  selector: 'app-share-link-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatSelectModule,
    MatOptionModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="sl-icon">share</mat-icon>
      {{ data.title }}
    </h2>
    <mat-dialog-content>
      @if (url()) {
        <p class="sl-hint">
          Anyone with this link can view the {{ data.targetType }} (read-only)
          until it expires.
        </p>
        <mat-form-field appearance="outline" class="sl-field">
          <mat-label>Share URL</mat-label>
          <input
            matInput
            readonly
            autocomplete="off"
            [value]="url()"
            (focus)="$any($event.target).select()"
          />
        </mat-form-field>
        <p class="sl-expiry">
          Expires
          @if (expiresAt()) {
            {{ expiresAt() | date:'medium' }}
          }
        </p>
      } @else {
        <p class="sl-hint">
          Pick how long the link should stay valid, then click Generate.
        </p>
        <mat-form-field appearance="outline" class="sl-field">
          <mat-label>Expires after</mat-label>
          <mat-select [(value)]="ttl">
            <mat-option [value]="60 * 60">1 hour</mat-option>
            <mat-option [value]="24 * 60 * 60">24 hours</mat-option>
            <mat-option [value]="7 * 24 * 60 * 60">7 days</mat-option>
            <mat-option [value]="30 * 24 * 60 * 60">30 days</mat-option>
          </mat-select>
        </mat-form-field>
        @if (error()) {
          <p class="sl-error">{{ error() }}</p>
        }
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Close</button>
      @if (url()) {
        <button mat-flat-button color="primary" type="button" (click)="copy()">
          <mat-icon>content_copy</mat-icon>
          Copy link
        </button>
      } @else {
        <button
          mat-flat-button
          color="primary"
          type="button"
          [disabled]="busy()"
          (click)="generate()"
        >
          {{ busy() ? 'Generating…' : 'Generate link' }}
        </button>
      }
    </mat-dialog-actions>
  `,
  styles: [`
    .sl-icon {
      vertical-align: middle;
      margin-right: 6px;
      color: var(--color-primary);
    }
    .sl-hint {
      margin: 0 0 12px;
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
    .sl-field { width: 100%; }
    .sl-expiry {
      margin: 0;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .sl-error {
      margin: 8px 0 0;
      padding: 8px 12px;
      background: var(--color-error-50, rgba(217, 48, 37, 0.06));
      color: var(--color-error-dark, #b3261e);
      border-radius: var(--card-border-radius, 8px);
      font-size: 13px;
    }
  `],
})
export class ShareLinkDialogComponent {
  private readonly http = inject(HttpClient);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);
  readonly data = inject<ShareLinkDialogData>(MAT_DIALOG_DATA);

  ttl = 24 * 60 * 60;
  readonly url = signal<string>('');
  readonly expiresAt = signal<string>('');
  readonly busy = signal<boolean>(false);
  readonly error = signal<string>('');

  generate(): void {
    this.busy.set(true);
    this.error.set('');
    this.http
      .post<ShareLinkResponse>('/api/share-links/', {
        target_type: this.data.targetType,
        target_id: String(this.data.targetId),
        expires_in_seconds: this.ttl,
      })
      .pipe(
        catchError((err) => {
          const status = err?.status;
          this.error.set(
            status === 404
              ? 'Share links are not yet configured on this server.'
              : (err?.error?.detail ?? 'Could not generate link.'),
          );
          return of<ShareLinkResponse | null>(null);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        this.busy.set(false);
        if (!res) return;
        this.url.set(res.url);
        this.expiresAt.set(res.expires_at);
      });
  }

  async copy(): Promise<void> {
    const v = this.url();
    if (!v) return;
    try {
      await navigator.clipboard.writeText(v);
      this.snack.open('Link copied to clipboard.', 'OK', { duration: 3000 });
    } catch {
      this.snack.open('Copy failed — select the field and press Ctrl+C.', 'Dismiss', {
        duration: 4000,
      });
    }
  }
}
