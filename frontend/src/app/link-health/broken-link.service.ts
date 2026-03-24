import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export type BrokenLinkStatus = 'open' | 'ignored' | 'fixed';

export interface BrokenLink {
  broken_link_id: string;
  source_content: number;
  source_content_title: string;
  source_content_url: string;
  url: string;
  http_status: number;
  redirect_url: string;
  first_detected_at: string;
  last_checked_at: string;
  status: BrokenLinkStatus;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface BrokenLinkFilters {
  status?: BrokenLinkStatus | 'all';
  http_status?: number | null;
  page?: number;
}

export interface ScanJob {
  job_id: string;
  message: string;
}

export interface PaginatedResult<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

@Injectable({ providedIn: 'root' })
export class BrokenLinkService {
  private http = inject(HttpClient);
  private base = '/api/broken-links/';

  list(filters: BrokenLinkFilters = {}): Observable<PaginatedResult<BrokenLink>> {
    let params = new HttpParams();

    if (filters.status && filters.status !== 'all') {
      params = params.set('status', filters.status);
    }
    if (filters.http_status !== undefined && filters.http_status !== null) {
      params = params.set('http_status', String(filters.http_status));
    }
    if (filters.page && filters.page > 1) {
      params = params.set('page', String(filters.page));
    }

    return this.http.get<PaginatedResult<BrokenLink>>(this.base, { params });
  }

  patch(
    id: string,
    payload: { status?: BrokenLinkStatus; notes?: string },
  ): Observable<BrokenLink> {
    return this.http.patch<BrokenLink>(`${this.base}${id}/`, payload);
  }

  startScan(): Observable<ScanJob> {
    return this.http.post<ScanJob>(`${this.base}scan/`, {});
  }

  exportCsv(filters: BrokenLinkFilters = {}): Observable<Blob> {
    let params = new HttpParams();

    if (filters.status && filters.status !== 'all') {
      params = params.set('status', filters.status);
    }
    if (filters.http_status !== undefined && filters.http_status !== null) {
      params = params.set('http_status', String(filters.http_status));
    }

    return this.http.get(`${this.base}export-csv/`, {
      params,
      responseType: 'blob',
    });
  }
}
