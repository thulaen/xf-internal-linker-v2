import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface FindBugsSummary {
  counts: { open: number; closed: number };
  severity: Record<string, number>;
  agents?: Record<string, number>;
  models?: Record<string, number>;
  last_run_at?: string | null;
  artifacts: { bytes: number; limit_bytes: number; retention_days: number };
  model?: { model?: string; status: string; reason?: string };
  model_batch?: {
    total: number;
    processed: number;
    remaining: number;
    state: string;
    updated_at?: string;
  };
  level_a: Record<string, number>;
}

export interface FindBugsFinding {
  id: number;
  title: string;
  status: string;
  severity: string;
  category?: string;
  category_key?: string;
  canonical_fingerprint: string;
  bug_pattern_id?: string;
  file?: string;
  affected_files?: string[];
  line?: number;
  confidence?: string;
  confirmed_by?: string;
  llm_candidate?: boolean;
  priority_score?: number;
  last_seen?: string;
  occurrence_count?: number;
  grouped_findings?: FindBugsFinding[];
  description?: string;
}

@Injectable({ providedIn: 'root' })
export class FindBugsService {
  private readonly http = inject(HttpClient);

  summary(): Observable<FindBugsSummary> {
    return this.http.get<FindBugsSummary>('/api/find-bugs/summary/');
  }

  findings(filters: Record<string, string> = {}): Observable<{ results: FindBugsFinding[] }> {
    let params = new HttpParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) params = params.set(key, value);
    });
    return this.http.get<{ results: FindBugsFinding[] }>('/api/find-bugs/findings/', { params });
  }

  runNow(): Observable<unknown> {
    return this.http.post('/api/find-bugs/run/', {});
  }

  importLatest(): Observable<unknown> {
    return this.http.post('/api/find-bugs/import-latest/', {});
  }

  pruneArtifacts(): Observable<unknown> {
    return this.http.post('/api/find-bugs/prune-artifacts/', {});
  }

  moveToLesson(issueId: number, classification: 'false_positive' | 'false_negative', lesson: string): Observable<unknown> {
    return this.http.post('/api/find-bugs/learned-lesson/', {
      issue_id: issueId,
      classification,
      lesson,
    });
  }

  confirmRealBug(issueId: number): Observable<unknown> {
    return this.http.post('/api/find-bugs/confirm/', { issue_id: issueId });
  }

  evaluateWithAgents(issueIds: number[], agent: string): Observable<unknown> {
    return this.http.post('/api/find-bugs/evaluate/', { issue_ids: issueIds, agent });
  }

  duplicateCheck(issueId: number): Observable<unknown> {
    return this.http.post('/api/find-bugs/duplicate-check/', { issue_id: issueId });
  }

  regressionCheck(issueId: number): Observable<unknown> {
    return this.http.post('/api/find-bugs/regression-check/', { issue_id: issueId });
  }

  generateReport(): Observable<unknown> {
    return this.http.post('/api/find-bugs/generate-report/', {});
  }

  syncContext(): Observable<unknown> {
    return this.http.post('/api/find-bugs/sync-context/', {});
  }

  createFixTask(issueId: number): Observable<unknown> {
    return this.http.post('/api/find-bugs/create-fix-task/', { issue_id: issueId });
  }

  assignAgent(issueId: number, agent: string): Observable<unknown> {
    return this.http.post('/api/find-bugs/assign-agent/', { issue_id: issueId, agent });
  }

  approveLesson(issueId: number): Observable<unknown> {
    return this.http.post('/api/find-bugs/approve-lesson/', { issue_id: issueId });
  }
}
