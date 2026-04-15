import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SyncJob {
  job_id: string;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  source: 'api' | 'jsonl' | 'wp';
  mode: string;
  file_name?: string;
  file_path?: string;
  progress: number; // Overall progress
  ingest_progress?: number;    // Phase 1
  ml_progress?: number;        // Total Phase 2
  spacy_progress?: number;     // Phase 2a
  embedding_progress?: number; // Phase 2b
  message: string;
  items_synced: number;
  items_updated: number;
  ml_items_queued: number;
  ml_items_completed: number;
  spacy_items_completed: number;
  embedding_items_completed: number;
  error_message?: string;
  checkpoint_stage: string;
  checkpoint_last_item_id?: number | null;
  checkpoint_items_processed: number;
  is_resumable: boolean;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface WebhookReceipt {
  receipt_id: string;
  source: string;
  event_type: string;
  status: string;
  error_message?: string;
  created_at: string;
}

@Injectable({
  providedIn: 'root',
})
export class SyncService {
  private apiUrl = '/api/sync-jobs/';

  constructor(private http: HttpClient) {}

  getJobs(): Observable<SyncJob[]> {
    return this.http.get<SyncJob[]>(this.apiUrl);
  }

  getJob(jobId: string): Observable<SyncJob> {
    return this.http.get<SyncJob>(`${this.apiUrl}${jobId}/`);
  }

  triggerApiSync(source: 'api' | 'wp', mode: string = 'full', scope_ids: number[] = []): Observable<{ job_id: string; source: string; mode: string }> {
    return this.http.post<{ job_id: string; source: string; mode: string }>(
      `${this.apiUrl}trigger_api_sync/`,
      { source, mode, scope_ids }
    );
  }

  pauseJob(jobId: string): Observable<{ job_id: string; status: string; is_resumable: boolean; message?: string }> {
    return this.http.post<{ job_id: string; status: string; is_resumable: boolean; message?: string }>(
      `${this.apiUrl}${jobId}/pause/`,
      {},
    );
  }

  resumeJob(jobId: string): Observable<{ job_id: string; status: string; is_resumable: boolean; checkpoint_stage?: string; message?: string }> {
    return this.http.post<{ job_id: string; status: string; is_resumable: boolean; checkpoint_stage?: string; message?: string }>(
      `${this.apiUrl}${jobId}/resume/`,
      {},
    );
  }

  uploadFile(file: File, mode: string): Observable<{ job_id: string; file: string; mode: string }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', mode);
    return this.http.post<{ job_id: string; file: string; mode: string }>('/api/import/upload/', formData);
  }

  getSourceStatus(): Observable<{ api: boolean; wp: boolean }> {
    return this.http.get<{ api: boolean; wp: boolean }>(`${this.apiUrl}source_status/`);
  }

  getWebhookReceipts(): Observable<WebhookReceipt[]> {
    return this.http.get<WebhookReceipt[]>('/api/webhook-receipts/');
  }

}
