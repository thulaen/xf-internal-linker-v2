/**
 * MCP / AI Agents service.
 *
 * Wraps the five backend endpoints powering the AI Agents (MCP) page:
 *
 *   GET  /api/mcp/health/          — is the MCP wiring alive?
 *   GET  /api/mcp/agents/          — install + config status of Claude Code / Codex / Antigravity
 *   POST /api/mcp/run-monthly/     — kick the monthly Top-50 Run Now button
 *   GET  /api/schedules/           — registered schedules + recent runs (sentient schedules)
 *   POST /api/schedules/<task>/run-now/  — manual fire of any registered schedule
 *
 * KISS: all methods return typed observables; no caching / polling baked in
 * here — components decide their own refresh cadence with `interval()` from
 * RxJS.
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { environment } from '../../../environments/environment';

/**
 * Standard error mapper for the MCP service. Every endpoint surfaces a plain-
 * English error so the UI can show "MCP server unreachable" instead of a raw
 * 0/500 stack trace. Components subscribe with `error: (msg) => ...`.
 */
function mapMcpError(label: string) {
  return (err: HttpErrorResponse) => {
    const detail =
      typeof err?.error === 'object' && err?.error?.detail
        ? String(err.error.detail)
        : err?.message || `HTTP ${err?.status}`;
    return throwError(() => new Error(`${label}: ${detail}`));
  };
}

export interface McpHealth {
  alive: boolean;
  as_of: string;
  mcp_json_present: boolean;
  server_script_present: boolean;
  mcp_python_pkg_installed: boolean;
  transport: string;
  tools_exposed: string[];
}

export interface AgentRow {
  name: string;
  installed: boolean;
  binary_on_path: boolean;
  supported: 'full' | 'best-effort' | string;
  configured_project?: boolean;
}

export interface AgentsResponse {
  claude_code: AgentRow;
  codex: AgentRow;
  antigravity: AgentRow & { name: string; supported: string };
}

export interface ScheduleRunSummary {
  scheduled_for: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';
  last_error: string;
  recovered_run: boolean;
}

export interface ScheduleSummary {
  task_name: string;
  cron_expr: string;
  description: string;
  next_run_at: string | null;
  recent_runs: ScheduleRunSummary[];
}

export interface SchedulesResponse {
  schedules: ScheduleSummary[];
}

export interface MonthlyReportSummary {
  month: string;
  filename: string;
  size_bytes: number;
  modified_at: string;
}

export interface MonthlyReportBody {
  month: string;
  filename: string;
  body: string;
}

@Injectable({ providedIn: 'root' })
export class McpService {
  private readonly http = inject(HttpClient);
  // environment.apiBaseUrl already includes the `/api` prefix.
  private readonly base = environment.apiBaseUrl;

  health(): Observable<McpHealth> {
    return this.http
      .get<McpHealth>(`${this.base}/mcp/health/`)
      .pipe(catchError(mapMcpError('MCP health check failed')));
  }

  agents(): Observable<AgentsResponse> {
    return this.http
      .get<AgentsResponse>(`${this.base}/mcp/agents/`)
      .pipe(catchError(mapMcpError('Failed to load AI-agent status')));
  }

  runMonthly(month?: string, strategy: 'auto' | 'python' | 'claude_code' = 'auto') {
    return this.http
      .post<{ queued: boolean; month: string; strategy: string }>(
        `${this.base}/mcp/run-monthly/`,
        { month, strategy },
      )
      .pipe(catchError(mapMcpError('Failed to queue monthly Top-50 run')));
  }

  schedules(): Observable<SchedulesResponse> {
    return this.http
      .get<SchedulesResponse>(`${this.base}/schedules/`)
      .pipe(catchError(mapMcpError('Failed to load schedules')));
  }

  runScheduleNow(taskName: string) {
    return this.http
      .post<{ queued: boolean; task_name: string }>(
        `${this.base}/schedules/${encodeURIComponent(taskName)}/run-now/`,
        {},
      )
      .pipe(catchError(mapMcpError(`Failed to run ${taskName} now`)));
  }

  listMonthlyReports(): Observable<{ reports: MonthlyReportSummary[] }> {
    return this.http
      .get<{ reports: MonthlyReportSummary[] }>(`${this.base}/reports/monthly/`)
      .pipe(catchError(mapMcpError('Failed to list monthly reports')));
  }

  readMonthlyReport(month: string): Observable<MonthlyReportBody> {
    return this.http
      .get<MonthlyReportBody>(`${this.base}/reports/monthly/${encodeURIComponent(month)}/`)
      .pipe(catchError(mapMcpError(`Failed to read report for ${month}`)));
  }
}
