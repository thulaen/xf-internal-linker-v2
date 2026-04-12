import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface BenchmarkResult {
  id: number;
  language: string;
  extension: string;
  function_name: string;
  input_size: string;
  mean_ns: number;
  median_ns: number;
  items_per_second: number;
  status: 'fast' | 'ok' | 'slow';
  threshold_ns: number | null;
}

export interface BenchmarkRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger: 'scheduled' | 'manual';
  status: 'running' | 'completed' | 'failed';
  summary_json: {
    total: number;
    fast: number;
    ok: number;
    slow: number;
    languages: { cpp: number; python: number };
  } | null;
  results: BenchmarkResult[];
}

export interface BenchmarkRunListItem {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger: string;
  status: string;
  result_count: number;
}

export interface BenchmarkTrendPoint {
  date: string;
  language: string;
  function: string;
  mean_ns: number;
  status: string;
}

@Injectable({ providedIn: 'root' })
export class PerformanceService {
  private http = inject(HttpClient);
  private baseUrl = '/api/benchmarks';

  getLatest(): Observable<BenchmarkRun> {
    return this.http.get<BenchmarkRun>(`${this.baseUrl}/latest/`).pipe(
      catchError(() => { throw new Error('Failed to load benchmark data'); })
    );
  }

  getRuns(): Observable<BenchmarkRunListItem[]> {
    return this.http.get<BenchmarkRunListItem[]>(`${this.baseUrl}/`).pipe(
      catchError(() => of([]))
    );
  }

  getRun(id: number): Observable<BenchmarkRun> {
    return this.http.get<BenchmarkRun>(`${this.baseUrl}/${id}/`).pipe(
      catchError(() => { throw new Error('Failed to load benchmark run'); })
    );
  }

  trigger(): Observable<{ id: number; status: string }> {
    return this.http.post<{ id: number; status: string }>(`${this.baseUrl}/trigger/`, {}).pipe(
      catchError(() => { throw new Error('Failed to trigger benchmark run'); })
    );
  }

  getReport(id: number): Observable<{ report: string }> {
    return this.http.get<{ report: string }>(`${this.baseUrl}/${id}/report/`).pipe(
      catchError(() => of({ report: 'Failed to generate report.' }))
    );
  }

  getTrends(): Observable<BenchmarkTrendPoint[]> {
    return this.http.get<BenchmarkTrendPoint[]>(`${this.baseUrl}/trends/`).pipe(
      catchError(() => of([]))
    );
  }
}
