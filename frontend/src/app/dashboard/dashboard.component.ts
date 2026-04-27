import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
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
import { FixRunbooksStripComponent } from './fix-runbooks-strip/fix-runbooks-strip.component';
// ── Phase D1 imports (Gaps 53-65) ────────────────────────────────────
import { StatusStoryComponent } from './status-story/status-story.component';
import { PriorityActionQueueComponent } from './priority-action-queue/priority-action-queue.component';
import { DailyQuizComponent } from './daily-quiz/daily-quiz.component';
import { CommandSuggestionsComponent } from './command-suggestions/command-suggestions.component';
import { ColorLegendComponent } from './color-legend/color-legend.component';
import { TaskToPageRouterComponent } from './task-to-page-router/task-to-page-router.component';
import { MissionBriefComponent } from './mission-brief/mission-brief.component';
import { HealthScoreDialComponent } from './health-score-dial/health-score-dial.component';
import { TrendDeltasComponent } from './trend-deltas/trend-deltas.component';
import { PrioritySummaryBellComponent } from './priority-summary-bell/priority-summary-bell.component';
import { TutorialCalloutComponent } from '../shared/ui/tutorial-callout/tutorial-callout.component';
// ── Phase D2 imports (Gaps 66-78) ────────────────────────────────────
import { OperatorChecklistComponent } from './operator-checklist/operator-checklist.component';
import { OneButtonResetComponent } from './one-button-reset/one-button-reset.component';
import { TipsOfDayComponent } from './tips-of-day/tips-of-day.component';
import { BehavioralNudgeComponent } from './behavioral-nudge/behavioral-nudge.component';
import { WeeklyDigestOptinComponent } from './weekly-digest-optin/weekly-digest-optin.component';
// ── Phase D3 imports (Gaps 152-187) ──────────────────────────────────
import { PersonalBarComponent } from './personal-bar/personal-bar.component';
import { InstantHealthComponent } from './instant-health/instant-health.component';
import { MetricTickerComponent } from './metric-ticker/metric-ticker.component';
import { QuickSearchBarComponent } from './quick-search-bar/quick-search-bar.component';
import { LauncherGridComponent } from './launcher-grid/launcher-grid.component';
import { RotatingCardComponent } from './rotating-cards/rotating-card.component';
import { WINS, AVOIDS, PITFALLS, QUOTES } from './rotating-cards/content-cards.data';
import { DashboardModeTogglesComponent } from './dashboard-mode-toggles/dashboard-mode-toggles.component';
import { SyncActivityComponent } from './sync-activity/sync-activity.component';
import { ScheduleWidgetComponent } from './schedule-widget/schedule-widget.component';
import { EmergencyStopComponent } from './emergency-stop/emergency-stop.component';
import { FlowDiagramComponent } from './flow-diagram/flow-diagram.component';
import { GoalTrackerComponent } from './goal-tracker/goal-tracker.component';
import { Eli5CardComponent } from './eli5-card/eli5-card.component';
import { QuietHoursIndicatorComponent } from './quiet-hours-indicator/quiet-hours-indicator.component';
import { WhosOnShiftComponent } from './whos-on-shift/whos-on-shift.component';
import { WhatsNewComponent } from './whats-new/whats-new.component';
import { DashboardModesService } from '../core/services/dashboard-modes.service';
import { YouAreHereComponent } from '../shared/ui/you-are-here/you-are-here.component';
import { RumSummaryComponent } from './rum-summary/rum-summary.component';
// Phase MC — Mission Critical section at top of dashboard.
import { MissionCriticalComponent } from './mission-critical/mission-critical.component';
// Skeleton placeholder for @defer blocks. Reused — single source of truth
// at frontend/src/app/shared/skeleton.
import { SkeletonComponent } from '../shared/skeleton/skeleton.component';

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
    FixRunbooksStripComponent,
    // Phase D1 / Gaps 53-65 — noob UX components.
    StatusStoryComponent,
    PriorityActionQueueComponent,
    DailyQuizComponent,
    CommandSuggestionsComponent,
    ColorLegendComponent,
    TaskToPageRouterComponent,
    MissionBriefComponent,
    HealthScoreDialComponent,
    TrendDeltasComponent,
    PrioritySummaryBellComponent,
    TutorialCalloutComponent,
    // Phase D2 — noob UX additions.
    OperatorChecklistComponent,
    OneButtonResetComponent,
    TipsOfDayComponent,
    BehavioralNudgeComponent,
    WeeklyDigestOptinComponent,
    // Phase D3 — KISS extensions (gaps 152-187).
    PersonalBarComponent,
    InstantHealthComponent,
    MetricTickerComponent,
    QuickSearchBarComponent,
    LauncherGridComponent,
    RotatingCardComponent,
    DashboardModeTogglesComponent,
    SyncActivityComponent,
    ScheduleWidgetComponent,
    EmergencyStopComponent,
    FlowDiagramComponent,
    GoalTrackerComponent,
    Eli5CardComponent,
    QuietHoursIndicatorComponent,
    WhosOnShiftComponent,
    WhatsNewComponent,
    YouAreHereComponent,
    // Phase OB / Gap 130 — RUM summary card.
    RumSummaryComponent,
    // Phase MC — Mission Critical tile grid.
    MissionCriticalComponent,
    // Reused skeleton for @defer placeholders.
    SkeletonComponent,
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
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
  private router = inject(Router);
  private destroyRef = inject(DestroyRef);
  private cdr = inject(ChangeDetectorRef);
  // Phase D3 / Gaps 161 + 167 — modes service exposed for the
  // template's calm-mode `@if` gates.
  modes = inject(DashboardModesService);

  // Phase D3 — rotating card snippet banks made template-accessible.
  readonly winsBank = WINS;
  readonly avoidsBank = AVOIDS;
  readonly pitfallsBank = PITFALLS;
  readonly quotesBank = QUOTES;

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
      .subscribe((events) => {
        this.activityEvents = events;
        this.cdr.markForCheck();
      });
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
      ref.onAction()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => {
          try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ }
        });
      ref.afterDismissed()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => {
          try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ }
        });
    }, 1500);
  }

  private loadOperatingDesk(): void {
    this.http.get<TodayAction[]>('/api/dashboard/today-actions/')
      .pipe(catchError(() => of([])), takeUntilDestroyed(this.destroyRef))
      .subscribe(actions => {
        this.todayActions = actions;
        this.cdr.markForCheck();
      });

    this.http.get<WhatChangedData>('/api/dashboard/what-changed/')
      .pipe(catchError(() => of(null)), takeUntilDestroyed(this.destroyRef))
      .subscribe(data => {
        this.whatChanged = data;
        this.cdr.markForCheck();
      });

    this.http.get<ResumeState>('/api/dashboard/resume-state/')
      .pipe(catchError(() => of(null)), takeUntilDestroyed(this.destroyRef))
      .subscribe(state => {
        this.resumeState = state;
        this.cdr.markForCheck();
      });

    this.http.get<{ runtime_mode: string; performance_mode: string; effective_runtime_mode?: string }>('/api/settings/runtime/')
      .pipe(catchError(() => of({ runtime_mode: 'cpu', performance_mode: 'balanced', effective_runtime_mode: 'cpu' })), takeUntilDestroyed(this.destroyRef))
      .subscribe(rt => {
        this.runtimeMode = rt.effective_runtime_mode ?? rt.runtime_mode;
        this.performanceMode = rt.performance_mode;
        this.perfModeSvc.setMode(rt.performance_mode);
        this.cdr.markForCheck();
      });
  }

  onPerformanceModeChange(mode: string): void {
    this.performanceMode = mode;
    this.perfModeSvc.setMode(mode);
  }

  resumeFromDashboard(id: string): void {
    const syncJob = this.resumeState?.resumable_syncs.find(job => job.job_id === id);
    if (syncJob) {
      this.syncSvc.resumeJob(id)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.snack.open('Resume queued. Open Jobs to watch progress.', 'Jobs', { duration: 6000 })
              .onAction()
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe(() => this.router.navigate(['/jobs']));
            this.loadOperatingDesk();
            this.cdr.markForCheck();
          },
          error: (err) => {
            const message = err?.error?.error || 'Could not resume that sync job.';
            this.snack.open(message, 'Dismiss', { duration: 5000 });
            this.cdr.markForCheck();
          },
        });
      return;
    }

    this.snack.open('Pipeline resume is not automated yet. Opening Jobs so you can inspect the run.', 'OK', { duration: 5000 });
    this.router.navigate(['/jobs']);
  }

  runMissedTask(taskName: string): void {
    this.snack.open(
      `${taskName} does not have a manual dashboard runbook yet. Opening Jobs for the available controls.`,
      'OK',
      { duration: 6000 },
    );
    this.router.navigate(['/jobs']);
  }

  deferMissedTask(taskName: string): void {
    this.snack.open(`${taskName} will run on its normal schedule.`, 'OK', { duration: 4000 });
  }

  load(): void {
    this.loading = true;
    this.dashSvc.refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (d) => {
          this.data = d;
          this.loading = false;
          this.daysSinceLastRun = this.computeDaysSinceLastRun(d.pipeline_runs);
          this.updateSetupChecklist(d);
          this.maybeShowSetupWizard(d);
          this.cdr.markForCheck();
        },
        error: () => {
          this.loading = false;
          this.snack.open('Failed to load dashboard', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
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
    this.syncSvc.getSourceStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status) => {
          const calls: string[] = [];
          if (status.api) calls.push('api');
          if (status.wp) calls.push('wp');
          if (calls.length === 0) {
            this.syncing = false;
            this.snack.open('No sources configured', 'Dismiss', { duration: 4000 });
            this.cdr.markForCheck();
            return;
          }
          let completed = 0;
          for (const source of calls) {
            this.syncSvc.triggerApiSync(source as 'api' | 'wp', 'full')
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe({
                next: () => {
                  completed++;
                  if (completed === calls.length) {
                    this.syncing = false;
                    this.snack.open(
                      'Sync started \u2014 check Jobs page for progress',
                      'Dismiss',
                      { duration: 5000 },
                    );
                    this.cdr.markForCheck();
                  }
                },
                error: () => {
                  completed++;
                  if (completed === calls.length) this.syncing = false;
                  this.snack.open(`Failed to sync ${source}`, 'Dismiss', { duration: 4000 });
                  this.cdr.markForCheck();
                },
              });
          }
        },
        error: () => {
          this.syncing = false;
          this.snack.open('Failed to check source status', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  runPipeline(): void {
    const ref = this.dialog.open<
      RunPipelineDialogComponent,
      void,
      RunPipelineDialogResult | null
    >(RunPipelineDialogComponent, { width: '420px' });

    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((result) => {
        if (!result) return;
        this.startingPipeline = true;
        this.suggSvc.startPipeline(result.rerunMode)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (run) => {
              this.startingPipeline = false;
              this.snack.open(
                `Pipeline started (run ${run.run_id.slice(0, 8)})`,
                'Dismiss',
                { duration: 5000 },
              );
              this.load();
              this.cdr.markForCheck();
            },
            error: () => {
              this.startingPipeline = false;
              this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
              this.cdr.markForCheck();
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
