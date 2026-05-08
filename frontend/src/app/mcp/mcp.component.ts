/**
 * AI Agents (MCP) page.
 *
 * Reachable from the sidenav at /mcp. Shows:
 *   1. Live MCP server status (poll /api/mcp/health/ every 5s)
 *   2. Per-agent connection rows (Claude Code / Codex / Antigravity)
 *   3. List of MCP tools exposed
 *   4. Sentient-schedules table (every registered schedule + recent runs)
 *   5. Monthly Top-50 "Run Now" button
 *
 * KISS: lightweight component, no router state, no signals beyond what we
 * really need. Polling uses RxJS interval() and is auto-cancelled via the
 * takeUntilDestroyed pattern.
 */
import { ChangeDetectionStrategy, Component, OnInit, signal, inject, DestroyRef } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, startWith, switchMap, catchError, of } from 'rxjs';

import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatTableModule } from '@angular/material/table';
import { MatSnackBar } from '@angular/material/snack-bar';

import {
  McpService,
  McpHealth,
  AgentsResponse,
  SchedulesResponse,
} from '../core/services/mcp.service';

@Component({
  selector: 'app-mcp',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatTableModule,
  ],
  templateUrl: './mcp.component.html',
  styleUrls: ['./mcp.component.scss'],
})
export class McpComponent implements OnInit {
  readonly health = signal<McpHealth | null>(null);
  readonly healthError = signal<string | null>(null);
  readonly agents = signal<AgentsResponse | null>(null);
  readonly schedules = signal<SchedulesResponse | null>(null);
  readonly runMonthlyBusy = signal(false);

  private readonly mcp = inject(McpService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  /**
   * Static catalogue of the MCP tools exposed by `backend/mcp_server.py`.
   * Plain-English descriptions so the user can see what the AI can do.
   * Order mirrors the order tools are declared in mcp_server.py.
   */
  readonly tools: ReadonlyArray<{ name: string; description: string }> = [
    {
      name: 'get_top_candidates',
      description:
        'Pull the top-N pending link suggestions for a given month, ordered by composite score.',
    },
    {
      name: 'get_dashboard_metrics',
      description: 'One-shot snapshot of suggestion-status counts and total volume.',
    },
    {
      name: 'list_orphans',
      description:
        'Return content items with zero approved or applied incoming links — useful for "which articles need links?" questions.',
    },
    {
      name: 'suggest_links',
      description:
        'Free-text query against pending suggestions — substring match on destination title, host sentence, and anchor phrase.',
    },
    {
      name: 'get_review_queue',
      description:
        'Suggestions in any lifecycle state (defaults to "pending"; pass "proposed" to see the AI-picked monthly batch awaiting human review).',
    },
    {
      name: 'search_content',
      description:
        'Find content items by title or URL (case-insensitive substring).',
    },
    {
      name: 'get_link_health',
      description:
        'One-shot health snapshot — counts of approved-live, stale-or-broken, and orphan items.',
    },
    {
      name: 'find_semantic_pairs',
      description:
        'Strongest co-navigation pairs from real GA4 session data, ranked by how often the same session visited both. Optional topic substring filter.',
    },
  ];

  ngOnInit(): void {
    // Poll health every 5s.
    interval(5000)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.mcp.health().pipe(
            catchError((err) => {
              this.healthError.set(this.errorMessage(err));
              return of(null);
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        if (res) {
          this.health.set(res);
          this.healthError.set(null);
        }
      });

    // One-shot fetches for agents + schedules. Schedules also refresh
    // every 30s so a running task moves from `running` → `succeeded`.
    this.mcp.agents().subscribe({
      next: (res) => this.agents.set(res),
      error: (err) => this.snack.open(`Could not load agents: ${this.errorMessage(err)}`, 'OK', { duration: 5000 }),
    });
    interval(30_000)
      .pipe(
        startWith(0),
        switchMap(() => this.mcp.schedules().pipe(catchError(() => of(null)))),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        if (res) this.schedules.set(res);
      });
  }

  runMonthlyNow(): void {
    if (this.runMonthlyBusy()) return;
    this.runMonthlyBusy.set(true);
    this.mcp.runMonthly().subscribe({
      next: (res) => {
        this.runMonthlyBusy.set(false);
        this.snack.open(
          `Monthly Top-50 queued for ${res.month} (strategy ${res.strategy}). Refresh the Schedules table to see progress.`,
          'OK',
          { duration: 6000 },
        );
      },
      error: (err) => {
        this.runMonthlyBusy.set(false);
        this.snack.open(`Could not queue monthly job: ${this.errorMessage(err)}`, 'OK', { duration: 6000 });
      },
    });
  }

  runScheduleNow(taskName: string): void {
    this.mcp.runScheduleNow(taskName).subscribe({
      next: () =>
        this.snack.open(`Queued ${taskName}. The Schedules table refreshes every 30s.`, 'OK', { duration: 4000 }),
      error: (err) => this.snack.open(`Could not run ${taskName}: ${this.errorMessage(err)}`, 'OK', { duration: 6000 }),
    });
  }

  agentRows(): { key: string; row: AgentsResponse[keyof AgentsResponse] }[] {
    const a = this.agents();
    if (!a) return [];
    return [
      { key: 'Claude Code', row: a.claude_code },
      { key: 'Codex', row: a.codex },
      { key: 'Antigravity', row: a.antigravity },
    ];
  }

  private errorMessage(err: unknown): string {
    if (err instanceof Error) return err.message;
    if (typeof err === 'object' && err !== null) {
      const e = err as { message?: string; statusText?: string };
      return e.message ?? e.statusText ?? 'unknown error';
    }
    return 'unknown error';
  }
}
