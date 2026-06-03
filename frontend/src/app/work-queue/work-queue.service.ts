import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export interface WorkQueueItem {
  key: string;
  kind: 'autoissue' | 'papertrail' | string;
  id: number;
  title: string;
  source: string;
  severity: string;
  status: string;
  priority_score: number;
  updated_at: string | null;
  affected_files: string[];
  blocked: boolean;
  business_impact: string;
  next_action: string;
}

export interface WorkQueueClaim {
  id: number;
  item_key: string;
  agent: string;
  status: string;
  conflict_reason: string;
  claimed_at: string;
}

export interface CauseGroup {
  fingerprint: string;
  title: string;
  sources: string[];
  source_count: number;
  issue_count: number;
  affected_files: string[];
  next_action: string;
}

export interface WorkQueueOverview {
  as_of: string;
  now: WorkQueueItem[];
  blocked: WorkQueueItem[];
  self_healing: Record<string, unknown>;
  live_signals: {
    stale_evidence_count: number;
    contradiction_count: number;
    source_confidence: Array<{ source: string; trust_score: number; reason: string }>;
  };
  agent_claims: WorkQueueClaim[];
  cause_groups: CauseGroup[];
  real_time_topics: string[];
}

@Injectable({ providedIn: 'root' })
export class WorkQueueService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  overview(): Observable<WorkQueueOverview> {
    return this.http.get<WorkQueueOverview>(`${this.base}/work-queue/overview/`);
  }

  rehearse(itemKey: string): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(
      `${this.base}/work-queue/tasks/${encodeURIComponent(itemKey)}/rehearse/`,
      {},
    );
  }
}

