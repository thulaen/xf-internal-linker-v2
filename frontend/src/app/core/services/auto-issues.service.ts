/**
 * AutoIssue HTTP client.
 *
 * Backed by the `/api/auto-issues/` ViewSet (apps.auto_issues.views).
 * Cross-source dedup means each row is one root cause regardless of how
 * many sources observed it — `source_observations` lists which sources
 * (glitchtip, agent, pyroscope) saw it. Read by `<error-log>` tab to
 * surface the registry without leaving the app.
 */

import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface SourceObservation {
  source: 'glitchtip' | 'pyroscope' | 'agent';
  external_id: string;
  first_seen: string;
  last_seen: string;
  occurrence_count: number;
}

export interface AutoIssue {
  id: number;
  source: 'glitchtip' | 'pyroscope' | 'agent';
  external_id: string;
  fingerprint: string;
  canonical_fingerprint: string;
  title: string;
  description: string;
  affected_files: string[];
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'open' | 'picked' | 'fixing' | 'resolved' | 'deferred';
  priority_score: number;
  occurrence_count: number;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
  resolved_by: string;
  fix_commit_sha: string;
  lessons_learned: string;
  source_observations: SourceObservation[];
}

interface PaginatedAutoIssues {
  count: number;
  next: string | null;
  previous: string | null;
  results: AutoIssue[];
}

export interface ResyncResponse {
  status: string;
  glitchtip_sync: Record<string, unknown>;
  glitchtip_picker: Record<string, unknown>;
  internal_picker: Record<string, unknown>;
  pyroscope_picker: Record<string, unknown>;
  open_count: number;
}

export interface FlushResponse {
  status: string;
  flushed_rows: number;
  glitchtip_sync: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class AutoIssuesService {
  private readonly http = inject(HttpClient);

  list(opts: { status?: 'open' | 'resolved'; source?: string } = {}): Observable<PaginatedAutoIssues> {
    let params = new HttpParams();
    if (opts.status) params = params.set('status', opts.status);
    if (opts.source) params = params.set('source', opts.source);
    return this.http.get<PaginatedAutoIssues>('/api/auto-issues/', { params });
  }

  /** Fire all three pickers + the GT mirror sync. Admin-only. */
  resync(): Observable<ResyncResponse> {
    return this.http.post<ResyncResponse>('/api/auto-issues/resync/', {});
  }

  /** Drop stale audit_errorlog rows older than 24h, force re-pull. Admin-only. */
  flushCache(): Observable<FlushResponse> {
    return this.http.post<FlushResponse>('/api/auto-issues/flush-cache/', {});
  }
}
