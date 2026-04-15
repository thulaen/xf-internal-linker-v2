import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, of } from 'rxjs';
import {
  DashboardService,
  DashboardData,
  PipelineRunSummary,
} from './dashboard.service';
import { SuggestionService } from '../review/suggestion.service';
import { SyncService } from '../jobs/sync.service';
import { RunPipelineDialogComponent, RunPipelineDialogResult } from '../core/run-pipeline-dialog.component';
import { SystemSummaryComponent } from './components/system-summary/system-summary.component';
import { WebhookLogComponent } from './components/webhook-log/webhook-log.component';
import { ScrollHighlightDirective } from '../core/directives/scroll-highlight.directive';
import { SetupWizardDialogComponent } from './components/setup-wizard/setup-wizard-dialog.component';
import { PulseService, SystemEvent } from '../core/services/pulse.service';
import { PerformanceModeService } from '../core/services/performance-mode.service';
import { TodayFocusComponent, TodayAction } from './today-focus/today-focus.component';
import { PickUpComponent, ResumeState } from './pick-up/pick-up.component';
import { RunningNowComponent } from './running-now/running-now.component';
import { WhatChangedComponent, WhatChangedData } from './what-changed/what-changed.component';
import { ReadyToRunComponent } from './ready-to-run/ready-to-run.component';
import { PerformanceModeComponent } from './performance-mode/performance-mode.component';
import { RuntimeModeComponent } from './runtime-mode/runtime-mode.component';
import { SystemMetricsComponent } from './system-metrics/system-metrics.component';
import { RankingStrategyCardComponent } from './ranking-strategy-card/ranking-strategy-card.component';
import { SuggestionFunnelComponent } from './suggestion-funnel/suggestion-funnel.component';
import { TopOpportunityPagesComponent } from './top-opportunity-pages/top-opportunity-pages.component';
import { FixRunbooksStripComponent } from './fix-runbooks-strip/fix-runbooks-strip.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatDialogModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
    SystemSummaryComponent,
    WebhookLogComponent,
    ScrollHighlightDirective,
    TodayFocusComponent,
    PickUpComponent,
    RunningNowComponent,
    WhatChangedComponent,
    ReadyToRunComponent,
    PerformanceModeComponent,
    RuntimeModeComponent,
    SystemMetricsComponent,
    RankingStrategyCardComponent,
    SuggestionFunnelComponent,
    TopOpportunityPagesComponent,
    FixRunbooksStripComponent,
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
})
export class DashboardComponent implements OnInit {
  private dashSvc = inject(DashboardService);
  private suggSvc = inject(SuggestionService);
  private syncSvc = inject(SyncService);
  private pulseService = inject(PulseService);
  private perfModeSvc = inject(PerformanceModeService);
  private http = inject(HttpClient);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  data: DashboardData | null = null;
  activityEvents: SystemEvent[] = [];
  loading = true;
  startingPipeline = false;
  syncing = false;
  daysSinceLastRun: number | null = null;

  // Stage 3 operating desk data
  todayActions: TodayAction[] = [];
  whatChanged: WhatChangedData | null = null;
  resumeState: ResumeState | null = null;
  runtimeMode = 'cpu';
  performanceMode = 'balanced';

  showSetupChecklist = false;
  setupSteps = { connected: false, imported: false, pipelineRan: false, reviewed: false };

  readonly runColumns = [
    'run_id', 'run_state', 'suggestions_created',
    'destinations_processed', 'duration_display', 'created_at',
  ];

  ngOnInit(): void {
    this.load();
    this.loadOperatingDesk();
    this.maybeShowFirstRunHint();

    // Subscribe to live activity feed.
    this.pulseService.events$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((events) => (this.activityEvents = events));
  }

  /**
   * One-time orientation toast for first-time users. Shows a friendly note
   * pointing out the Performance Mode card. Persisted via localStorage so it
   * never repeats.
   */
  private maybeShowFirstRunHint(): void {
    const KEY = 'xf.perfMode.firstRunSeen';
    try {
      if (localStorage.getItem(KEY)) return;
    } catch {
      return; // no storage, skip silently
    }
    // Delay so the toast does not fight the setup wizard on brand-new installs.
    setTimeout(() => {
      const ref = this.snack.open(
        'Tip: the card labelled "Performance Mode" lets you make the linker quieter or faster in one click.',
        'Got it',
        { duration: 8000 },
      );
      ref.onAction().subscribe(() => {
        try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ }
      });
      ref.afterDismissed().subscribe(() => {
        try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ }
      });
    }, 1500);
  }

  private loadOperatingDesk(): void {
    this.http.get<TodayAction[]>('/api/dashboard/today-actions/')
      .pipe(catchError(() => of([])))
      .subscribe(actions => this.todayActions = actions);

    this.http.get<WhatChangedData>('/api/dashboard/what-changed/')
      .pipe(catchError(() => of(null)))
      .subscribe(data => this.whatChanged = data);

    this.http.get<ResumeState>('/api/dashboard/resume-state/')
      .pipe(catchError(() => of(null)))
      .subscribe(state => this.resumeState = state);

    this.http.get<{ runtime_mode: string; performance_mode: string }>('/api/settings/runtime/')
      .pipe(catchError(() => of({ runtime_mode: 'cpu', performance_mode: 'balanced' })))
      .subscribe(rt => {
        this.runtimeMode = rt.runtime_mode;
        this.performanceMode = rt.performance_mode;
        this.perfModeSvc.setMode(rt.performance_mode);
      });
  }

  onPerformanceModeChange(mode: string): void {
    this.performanceMode = mode;
    this.perfModeSvc.setMode(mode);
  }

  load(): void {
    this.loading = true;
    this.dashSvc.refresh().subscribe({
      next: (d) => {
        this.data = d;
        this.loading = false;
        this.daysSinceLastRun = this.computeDaysSinceLastRun(d.pipeline_runs);
        this.updateSetupChecklist(d);
        this.maybeShowSetupWizard(d);
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load dashboard', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private computeDaysSinceLastRun(runs: PipelineRunSummary[]): number | null {
    const lastCompleted = runs.find(r => r.run_state === 'completed');
    if (!lastCompleted) return null;
    const diffMs = Date.now() - new Date(lastCompleted.created_at).getTime();
    return Math.floor(diffMs / (1000 * 60 * 60 * 24));
  }

  catchUpSync(): void {
    this.syncing = true;
    this.syncSvc.getSourceStatus().subscribe({
      next: (status) => {
        const calls: string[] = [];
        if (status.api) calls.push('api');
        if (status.wp) calls.push('wp');
        if (calls.length === 0) {
          this.syncing = false;
          this.snack.open('No sources configured', 'Dismiss', { duration: 4000 });
          return;
        }
        let completed = 0;
        for (const source of calls) {
          this.syncSvc.triggerApiSync(source as 'api' | 'wp', 'full').subscribe({
            next: () => {
              completed++;
              if (completed === calls.length) {
                this.syncing = false;
                this.snack.open(
                  'Sync started \u2014 check Jobs page for progress',
                  'Dismiss',
                  { duration: 5000 },
                );
              }
            },
            error: () => {
              completed++;
              if (completed === calls.length) this.syncing = false;
              this.snack.open(`Failed to sync ${source}`, 'Dismiss', { duration: 4000 });
            },
          });
        }
      },
      error: () => {
        this.syncing = false;
        this.snack.open('Failed to check source status', 'Dismiss', { duration: 4000 });
      },
    });
  }

  runPipeline(): void {
    const ref = this.dialog.open<
      RunPipelineDialogComponent,
      void,
      RunPipelineDialogResult | null
    >(RunPipelineDialogComponent, { width: '420px' });

    ref.afterClosed().subscribe((result) => {
      if (!result) return;
      this.startingPipeline = true;
      this.suggSvc.startPipeline(result.rerunMode).subscribe({
        next: (run) => {
          this.startingPipeline = false;
          this.snack.open(
            `Pipeline started (run ${run.run_id.slice(0, 8)})`,
            'Dismiss',
            { duration: 5000 },
          );
          this.load();
        },
        error: () => {
          this.startingPipeline = false;
          this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
        },
      });
    });
  }

  stateColor(state: string): string {
    switch (state) {
      case 'completed': return 'success';
      case 'running':   return 'primary';
      case 'failed':    return 'warn';
      default:          return '';
    }
  }

  stateIcon(state: string): string {
    switch (state) {
      case 'completed': return 'check_circle';
      case 'running':   return 'sync';
      case 'failed':    return 'error';
      case 'queued':    return 'schedule';
      default:          return 'help_outline';
    }
  }

  trackByRunId(_: number, r: PipelineRunSummary): string {
    return r.run_id;
  }

  private updateSetupChecklist(d: DashboardData): void {
    const dismissed = localStorage.getItem('setupChecklistDismissed') === 'true';
    this.setupSteps = {
      connected: d.content_count > 0 || d.recent_imports.some(j => j.status === 'completed'),
      imported: d.content_count > 0,
      pipelineRan: d.pipeline_runs.length > 0,
      reviewed: d.suggestion_counts.approved + d.suggestion_counts.applied > 0,
    };
    const allDone = this.setupSteps.connected && this.setupSteps.imported
      && this.setupSteps.pipelineRan && this.setupSteps.reviewed;
    this.showSetupChecklist = !dismissed && !allDone;
  }

  private maybeShowSetupWizard(d: DashboardData): void {
    const shown = localStorage.getItem('setupWizardCompleted') === 'true';
    if (!shown && d.content_count === 0) {
      localStorage.setItem('setupWizardCompleted', 'true');
      this.dialog.open(SetupWizardDialogComponent, { width: '520px', disableClose: false });
    }
  }

  dismissSetupChecklist(): void {
    this.showSetupChecklist = false;
    localStorage.setItem('setupChecklistDismissed', 'true');
  }

  getImportSettingsFragment(source: string): string {
    switch (source) {
      case 'api': return 'xenforo-settings';
      case 'wp':  return 'wordpress-settings';
      default:    return '';
    }
  }
}
