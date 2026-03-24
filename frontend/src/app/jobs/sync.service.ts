import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SyncJob {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  source: 'api' | 'jsonl' | 'wp';
  mode: string;
  file_name?: string;
  progress: number;
  message: string;
  items_synced: number;
  items_updated: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
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

  uploadFile(file: File, mode: string): Observable<{ job_id: string; file: string; mode: string }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', mode);
    return this.http.post<{ job_id: string; file: string; mode: string }>('/api/import/upload/', formData);
  }
}
