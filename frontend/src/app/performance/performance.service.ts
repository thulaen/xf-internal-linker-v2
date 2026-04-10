import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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
    languages: { cpp: number; python: number; csharp: number };
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
    return this.http.get<BenchmarkRun>(`${this.baseUrl}/latest/`);
  }

  getRuns(): Observable<BenchmarkRunListItem[]> {
    return this.http.get<BenchmarkRunListItem[]>(`${this.baseUrl}/`);
  }

  getRun(id: number): Observable<BenchmarkRun> {
    return this.http.get<BenchmarkRun>(`${this.baseUrl}/${id}/`);
  }

  trigger(): Observable<{ id: number; status: string }> {
    return this.http.post<{ id: number; status: string }>(`${this.baseUrl}/trigger/`, {});
  }

  getReport(id: number): Observable<{ report: string }> {
    return this.http.get<{ report: string }>(`${this.baseUrl}/${id}/report/`);
  }

  getTrends(): Observable<BenchmarkTrendPoint[]> {
    return this.http.get<BenchmarkTrendPoint[]>(`${this.baseUrl}/trends/`);
  }
}
