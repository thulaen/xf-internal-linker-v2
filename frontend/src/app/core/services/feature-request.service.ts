import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable } from 'rxjs';

/**
 * Phase GB / Gap 151 — Feature-Request inbox client.
 *
 * Thin wrapper over `/api/feature-requests/` endpoints. Handles three
 * flows:
 *
 *   • submit()        — operator submits a new request
 *   • list()          — Preference-Center and admin triage read queue
 *   • vote() / unvote — idempotent upvote toggle
 *
 * The service attaches a tiny environmental context to every POST so
 * maintainers can reproduce without emailing back and forth. The
 * context is additive — the backend also captures user-agent + IP.
 */

export type FeatureRequestPriority = 'low' | 'medium' | 'high';
export type FeatureRequestStatus =
  | 'new'
  | 'accepted'
  | 'planned'
  | 'shipped'
  | 'declined'
  | 'duplicate';

export interface FeatureRequest {
  id: number;
  created_at: string;
  updated_at: string;
  author: number | null;
  author_username: string;
  title: string;
  body: string;
  category: string;
  priority: FeatureRequestPriority;
  status: FeatureRequestStatus;
  context: Record<string, unknown>;
  votes: number;
  admin_reply: string;
  has_voted: boolean;
}

export interface FeatureRequestPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: FeatureRequest[];
}

export interface FeatureRequestSubmit {
  title: string;
  body: string;
  category?: string;
  priority?: FeatureRequestPriority;
}

@Injectable({ providedIn: 'root' })
export class FeatureRequestService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private readonly base = '/api/feature-requests/';

  list(status?: FeatureRequestStatus): Observable<FeatureRequestPage> {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    return this.http.get<FeatureRequestPage>(this.base + qs);
  }

  submit(input: FeatureRequestSubmit): Observable<FeatureRequest> {
    const context = this.captureContext();
    return this.http.post<FeatureRequest>(this.base, {
      title: input.title,
      body: input.body,
      category: input.category ?? '',
      priority: input.priority ?? 'medium',
      context,
    });
  }

  vote(id: number): Observable<{ votes: number; has_voted: boolean }> {
    return this.http.post<{ votes: number; has_voted: boolean }>(
      `${this.base}${id}/vote/`,
      {},
    );
  }

  unvote(id: number): Observable<{ votes: number; has_voted: boolean }> {
    return this.http.post<{ votes: number; has_voted: boolean }>(
      `${this.base}${id}/unvote/`,
      {},
    );
  }

  /** Tiny client context so maintainers know which screen the user was on. */
  private captureContext(): Record<string, unknown> {
    const w = typeof window !== 'undefined' ? window : undefined;
    return {
      route: this.router.url,
      locale: typeof navigator !== 'undefined' ? navigator.language : '',
      screen:
        w?.screen
          ? `${w.screen.width}x${w.screen.height}@${w.devicePixelRatio ?? 1}`
          : '',
      viewport: w ? `${w.innerWidth}x${w.innerHeight}` : '',
      timezone: this.safeTimezone(),
      client_submitted_at: new Date().toISOString(),
    };
  }

  private safeTimezone(): string {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch {
      return '';
    }
  }
}
