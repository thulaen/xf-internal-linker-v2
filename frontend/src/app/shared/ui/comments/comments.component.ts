import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Input,
  OnChanges,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpParams } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { catchError, of } from 'rxjs';

import { TimeAgoPipe } from '../../pipes/time-ago.pipe';

/**
 * Phase DC / Gaps 128 + 129 — Entity comments with @mentions.
 *
 * Lists comments for a given (targetType, targetId) and lets the
 * current user post a new one. `@username` substrings in the body
 * render as highlighted links; the backend extracts the usernames
 * at save time and triggers notifications (existing
 * `apps.notifications` app hooks, not handled here).
 *
 * Backend API expected:
 *   GET  /api/entity-comments/?target_type=...&target_id=...
 *   POST /api/entity-comments/      { target_type, target_id, body }
 *
 * Until the endpoints ship, the GET call silently yields an empty
 * list and the POST surfaces a friendly error — the surrounding UI
 * still renders cleanly (no crashes, no blank states).
 */

interface EntityCommentDto {
  id: number;
  created_at: string;
  target_type: string;
  target_id: string;
  author: { id: number; username: string } | null;
  body: string;
  mentions: string[];
  parent: number | null;
  resolved: boolean;
}

@Component({
  selector: 'app-comments',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    TimeAgoPipe,
  ],
  template: `
    <section class="cm">
      <header class="cm-head">
        <mat-icon aria-hidden="true">forum</mat-icon>
        <h3 class="cm-title">
          {{ comments().length }} comment{{ comments().length === 1 ? '' : 's' }}
        </h3>
      </header>

      @if (comments().length > 0) {
        <ol class="cm-list">
          @for (c of comments(); track c.id) {
            <li class="cm-item">
              <div class="cm-meta">
                <span class="cm-author">{{ c.author?.username || 'anonymous' }}</span>
                <span class="cm-time">{{ c.created_at | timeAgo }}</span>
              </div>
              <div class="cm-body" [innerHTML]="formatBody(c.body)"></div>
            </li>
          }
        </ol>
      } @else {
        <p class="cm-empty">No comments yet. Be the first.</p>
      }

      <footer class="cm-footer">
        <mat-form-field appearance="outline" class="cm-field">
          <mat-label>Add a comment</mat-label>
          <textarea
            matInput
            rows="3"
            [(ngModel)]="draft"
            [disabled]="posting()"
            placeholder="Write a comment. Use @username to mention a teammate."
          ></textarea>
        </mat-form-field>
        @if (postError()) {
          <p class="cm-error">{{ postError() }}</p>
        }
        <div class="cm-footer-actions">
          <button
            mat-flat-button
            color="primary"
            type="button"
            [disabled]="posting() || draft.trim().length === 0"
            (click)="post()"
          >
            <mat-icon>send</mat-icon>
            {{ posting() ? 'Posting…' : 'Post' }}
          </button>
        </div>
      </footer>
    </section>
  `,
  styles: [`
    .cm { display: flex; flex-direction: column; gap: 12px; }
    .cm-head {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .cm-head mat-icon { color: var(--color-primary); }
    .cm-title {
      margin: 0;
      font-size: 14px;
      font-weight: 500;
    }
    .cm-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .cm-item {
      padding: 10px 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .cm-meta {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
      font-size: 11px;
    }
    .cm-author { font-weight: 500; color: var(--color-text-primary); }
    .cm-time { color: var(--color-text-secondary); }
    .cm-body {
      font-size: 13px;
      line-height: 1.55;
      color: var(--color-text-primary);
      white-space: pre-wrap;
    }
    .cm-body ::ng-deep .cm-mention {
      color: var(--color-primary);
      font-weight: 500;
      text-decoration: none;
    }
    .cm-empty {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
    .cm-footer {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .cm-field { width: 100%; }
    .cm-footer-actions {
      display: flex;
      justify-content: flex-end;
    }
    .cm-error {
      margin: 0;
      padding: 6px 10px;
      background: var(--color-error-50, rgba(217, 48, 37, 0.06));
      color: var(--color-error-dark, #b3261e);
      border-radius: var(--card-border-radius, 8px);
      font-size: 12px;
    }
  `],
})
export class CommentsComponent implements OnChanges {
  @Input({ required: true }) targetType = '';
  @Input({ required: true }) targetId: string | number = '';

  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  readonly comments = signal<readonly EntityCommentDto[]>([]);
  readonly posting = signal<boolean>(false);
  readonly postError = signal<string>('');
  draft = '';

  ngOnChanges(): void {
    if (!this.targetType || !this.targetId) return;
    this.fetch();
  }

  fetch(): void {
    const params = new HttpParams()
      .set('target_type', this.targetType)
      .set('target_id', String(this.targetId));
    this.http
      .get<EntityCommentDto[] | { results: EntityCommentDto[] }>(
        '/api/entity-comments/',
        { params },
      )
      .pipe(
        catchError(() => of<EntityCommentDto[]>([])),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((raw) => {
        const arr = Array.isArray(raw)
          ? raw
          : ((raw as { results?: EntityCommentDto[] })?.results ?? []);
        this.comments.set(arr);
      });
  }

  post(): void {
    const body = this.draft.trim();
    if (!body || this.posting()) return;
    this.posting.set(true);
    this.postError.set('');
    this.http
      .post<EntityCommentDto>('/api/entity-comments/', {
        target_type: this.targetType,
        target_id: String(this.targetId),
        body,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (comment) => {
          this.posting.set(false);
          this.draft = '';
          this.comments.set([...this.comments(), comment]);
        },
        error: (err) => {
          this.posting.set(false);
          this.postError.set(
            err?.status === 404
              ? 'Comments are not yet configured on this server.'
              : err?.error?.detail ?? 'Could not post comment.',
          );
        },
      });
  }

  /** Phase DC / Gap 129 — Render @mentions as styled <span>s. */
  formatBody(body: string): string {
    const escaped = body
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    return escaped.replace(
      /(^|[\s(,;])@([A-Za-z0-9_.-]{2,50})/g,
      '$1<span class="cm-mention">@$2</span>',
    );
  }
}
