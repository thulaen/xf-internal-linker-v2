/**
 * SpecViewerDialog — read-only Material dialog that fetches a repo
 * markdown spec from `GET /api/docs/specs/<slug>/` and shows it
 * inside the existing app shell.
 *
 * Wired from the FR-099–FR-105 settings cards via the "View spec"
 * button (masterplan Group A.5). The dialog is scrollable, has a
 * single Close action, and surfaces fetch errors as a plain-English
 * message — no jargon, no stack traces leak through.
 *
 * The backend renders the markdown to safe HTML server-side using
 * the `markdown` Python package (see `backend/apps/core/views_docs.py`)
 * so the frontend just binds via `[innerHTML]`. Source files come
 * from this repo's own `docs/specs/` and the slug is path-traversal
 * guarded server-side, so DomSanitizer's default trust is acceptable.
 */
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { catchError, of } from 'rxjs';

/** Data passed when opening the dialog. */
export interface SpecViewerDialogData {
  /** Slug of the spec file (no `.md` suffix). Allow-listed server-side. */
  readonly specSlug: string;
  /** Pretty short label for the dialog title (e.g. "DARB"). Falls back to the spec's own H1 once it loads. */
  readonly fallbackTitle?: string;
}

/** Server response shape. Matches `views_docs.view_spec_markdown`. */
interface SpecResponse {
  slug: string;
  title: string;
  html: string;
  raw: string;
}

@Component({
  selector: 'app-spec-viewer-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>
      {{ headerTitle() }}
    </h2>
    <mat-dialog-content class="spec-content">
      @if (loading()) {
        <div class="spec-loading">
          <mat-spinner diameter="32"></mat-spinner>
          <span>Loading spec…</span>
        </div>
      } @else if (errorMessage()) {
        <div class="spec-error">
          <mat-icon>error_outline</mat-icon>
          <div>
            <p class="spec-error-headline">Could not load this spec.</p>
            <p class="spec-error-detail">{{ errorMessage() }}</p>
          </div>
        </div>
      } @else {
        <article class="spec-body" [innerHTML]="html()"></article>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-flat-button color="primary" mat-dialog-close>Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .spec-content {
      max-height: 70vh;
      overflow-y: auto;
      padding: var(--space-md) var(--space-lg);
    }
    .spec-loading {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      justify-content: center;
      padding: var(--space-xl);
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .spec-error {
      display: flex;
      align-items: flex-start;
      gap: var(--space-sm);
      padding: var(--space-md);
      border-radius: 8px;
      background: var(--color-error-50, #fce8e6);
      color: var(--color-error-dark, #b3261e);
    }
    .spec-error mat-icon { margin-top: 2px; }
    .spec-error-headline {
      margin: 0 0 var(--space-xs);
      font-weight: 600;
      font-size: 13px;
    }
    .spec-error-detail {
      margin: 0;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .spec-body {
      font-size: 13px;
      line-height: 1.6;
      color: var(--color-text-primary);
    }
    .spec-body :first-child { margin-top: 0; }
    .spec-body h1, .spec-body h2, .spec-body h3 {
      color: var(--color-text-primary);
      margin-top: var(--space-lg);
    }
    .spec-body h1 { font-size: 22px; }
    .spec-body h2 { font-size: 18px; }
    .spec-body h3 { font-size: 15px; }
    .spec-body code {
      font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
      background: var(--color-blue-50, #e8f0fe);
      padding: 2px 4px;
      border-radius: 4px;
      font-size: 12px;
    }
    .spec-body pre {
      background: var(--color-blue-50, #e8f0fe);
      padding: var(--space-md);
      border-radius: 8px;
      overflow-x: auto;
      font-size: 12px;
    }
    .spec-body pre code { background: none; padding: 0; }
    .spec-body table {
      border-collapse: collapse;
      margin: var(--space-md) 0;
    }
    .spec-body th, .spec-body td {
      border: 0.8px solid var(--card-border-color, #dadce0);
      padding: var(--space-xs) var(--space-sm);
      text-align: left;
    }
    .spec-body a {
      color: var(--color-primary, #1a73e8);
    }
  `],
})
export class SpecViewerDialogComponent {
  private readonly data = inject<SpecViewerDialogData>(MAT_DIALOG_DATA);
  private readonly dialogRef = inject(MatDialogRef<SpecViewerDialogComponent>);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly loading = signal(true);
  protected readonly errorMessage = signal<string>('');
  protected readonly serverTitle = signal<string>('');
  protected readonly html = signal<string>('');

  /** Use the server-provided title if it loaded; else fall back to caller-supplied. */
  protected readonly headerTitle = computed(() => {
    const fromServer = this.serverTitle();
    if (fromServer) return fromServer;
    return this.data.fallbackTitle?.trim() || 'Spec';
  });

  constructor() {
    const slug = (this.data.specSlug || '').trim();
    if (!slug) {
      this.loading.set(false);
      this.errorMessage.set('No spec key was provided. Please report this to the developer.');
      return;
    }
    this.fetchSpec(slug);
  }

  private fetchSpec(slug: string): void {
    this.http
      .get<SpecResponse>(`/api/docs/specs/${encodeURIComponent(slug)}/`)
      .pipe(
        catchError((err) => {
          // Server returns {detail: "..."} on 404/500 — surface that
          // verbatim so the user gets a plain-English explanation.
          const detail =
            err?.error?.detail ||
            err?.message ||
            'The server did not respond. Try again in a moment.';
          this.errorMessage.set(String(detail));
          return of(null);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        this.loading.set(false);
        if (res === null) return;
        this.serverTitle.set(res.title || '');
        this.html.set(res.html || '');
      });
  }
}
